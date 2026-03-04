"""Claude AI Agent - core orchestrator with tool-calling loop."""

import asyncio
from collections.abc import Callable, Coroutine, Iterable
from uuid import uuid4

import anthropic
import anthropic.types
import structlog

from app.core.config import get_settings
from app.orchestrator.model_router import record_cost, select_model
from app.orchestrator.prompt_builder import build_system_prompt
from app.orchestrator.tool_registry import ToolRegistry
from app.schemas.orchestrator import (
    OrchestratorRequest,
    OrchestratorResponse,
    ToolCall,
    ToolResult,
)

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

# Maximum number of tool-calling iterations to prevent infinite loops
MAX_ITERATIONS: int = 10

# Retry configuration for Claude API errors
_MAX_RETRIES: int = 3
_RETRY_BACKOFF_SECONDS: list[float] = [1.0, 2.0, 4.0]

# Type alias for progress callback
ProgressCallback = Callable[[str, int, int], Coroutine[object, object, None]]


class OrchestratorError(Exception):
    """Base error for orchestrator operations."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class MaxIterationsReachedError(OrchestratorError):
    """Raised when the tool-calling loop exceeds maximum iterations."""

    def __init__(self) -> None:
        super().__init__(f"Tool-calling loop exceeded maximum {MAX_ITERATIONS} iterations")


class ClaudeAPIError(OrchestratorError):
    """Raised when Claude API returns an unrecoverable error."""


class OrchestratorAgent:
    """Claude AI Agent with tool-calling loop.

    Manages the conversation with Claude API, executes tool calls,
    and returns final responses. Supports streaming progress updates
    via a callback mechanism.
    """

    def __init__(self, tool_registry: ToolRegistry) -> None:
        self._registry = tool_registry
        settings = get_settings()
        self._client: anthropic.AsyncAnthropic | anthropic.AsyncAnthropicBedrock
        if settings.use_bedrock:
            self._client = anthropic.AsyncAnthropicBedrock(
                aws_access_key=settings.aws_access_key_id,
                aws_secret_key=settings.aws_secret_access_key,
                aws_region=settings.aws_region,
            )
        else:
            self._client = anthropic.AsyncAnthropic(
                api_key=settings.anthropic_api_key,
            )
        # Session-based conversation history
        self._conversations: dict[str, list[anthropic.types.MessageParam]] = {}

    async def process_message(
        self,
        request: OrchestratorRequest,
        *,
        progress_callback: ProgressCallback | None = None,
        host_status: str | None = None,
        user_memories: str | None = None,
    ) -> OrchestratorResponse:
        """Process a user message through the AI orchestrator.

        Runs the tool-calling loop: sends message to Claude, executes
        any tool calls, sends results back, and repeats until Claude
        produces a final text response or max iterations is reached.

        Args:
            request: Orchestrator request with user message.
            progress_callback: Optional async callback for progress updates.
            host_status: Formatted agent status for system prompt.
            user_memories: Formatted user memories for system prompt.

        Returns:
            OrchestratorResponse with the final AI response.

        Raises:
            MaxIterationsReachedError: If loop exceeds MAX_ITERATIONS.
            ClaudeAPIError: If Claude API returns an unrecoverable error.
        """
        # Select model based on message complexity
        router_result = select_model(request.message)
        model = router_result.model

        await logger.ainfo(
            "orchestrator_model_selected",
            session_id=request.session_id,
            model=model,
            tier=router_result.tier.value,
            reason=router_result.reason,
            complexity_score=router_result.complexity_score,
            is_override=router_result.is_override,
            is_fallback=router_result.is_fallback,
        )

        # Build system prompt with dynamic context
        system_prompt = build_system_prompt(
            host_status=host_status,
            user_memories=user_memories,
        )

        # Get or create conversation history
        conversation = self._get_conversation(request.session_id)

        # Add user message to conversation
        user_msg: anthropic.types.MessageParam = {
            "role": "user",
            "content": request.message,
        }
        conversation.append(user_msg)

        # Get tools for API
        tools = self._registry.get_tools_for_api()

        # Tool-calling loop
        total_input_tokens = 0
        total_output_tokens = 0
        tool_calls_count = 0
        final_text = ""

        for iteration in range(MAX_ITERATIONS):
            await logger.ainfo(
                "orchestrator_iteration",
                session_id=request.session_id,
                iteration=iteration + 1,
                max_iterations=MAX_ITERATIONS,
            )

            # Call Claude API with retry
            response = await self._call_claude_api(
                model=model,
                system=system_prompt,
                messages=conversation,
                tools=tools,
            )

            # Track token usage
            total_input_tokens += response.usage.input_tokens
            total_output_tokens += response.usage.output_tokens

            # Process response
            has_tool_use = False
            text_parts: list[str] = []
            tool_result_blocks: list[anthropic.types.ToolResultBlockParam] = []

            for block in response.content:
                if block.type == "text":
                    text_parts.append(block.text)
                elif block.type == "tool_use":
                    has_tool_use = True
                    tool_calls_count += 1

                    tool_call = ToolCall(
                        id=block.id,
                        name=block.name,
                        input=dict(block.input),
                    )

                    # Send progress update
                    if progress_callback is not None:
                        await progress_callback(
                            tool_call.name,
                            iteration + 1,
                            MAX_ITERATIONS,
                        )

                    # Execute tool
                    result = await self._execute_tool(tool_call)
                    tool_result_block: anthropic.types.ToolResultBlockParam = {
                        "type": "tool_result",
                        "tool_use_id": result.tool_use_id,
                        "content": result.content,
                        "is_error": result.is_error,
                    }
                    tool_result_blocks.append(tool_result_block)

            if has_tool_use:
                # Add assistant response to conversation
                assistant_msg: anthropic.types.MessageParam = {
                    "role": "assistant",
                    "content": response.content,
                }
                conversation.append(assistant_msg)
                # Add tool results to conversation
                tool_user_msg: anthropic.types.MessageParam = {
                    "role": "user",
                    "content": tool_result_blocks,
                }
                conversation.append(tool_user_msg)
            else:
                # No tool calls - this is the final response
                final_text = " ".join(text_parts)

                # Add assistant response to conversation
                final_msg: anthropic.types.MessageParam = {
                    "role": "assistant",
                    "content": final_text,
                }
                conversation.append(final_msg)
                break
        else:
            # Max iterations reached without a final text response
            await logger.awarning(
                "orchestrator_max_iterations_reached",
                session_id=request.session_id,
                iterations=MAX_ITERATIONS,
            )
            # Force a final response
            force_msg: anthropic.types.MessageParam = {
                "role": "user",
                "content": ("Maksimum islem limiti asildi. Lutfen son cevabini ver."),
            }
            conversation.append(force_msg)
            response = await self._call_claude_api(
                model=model,
                system=system_prompt,
                messages=conversation,
                tools=tools,
            )
            total_input_tokens += response.usage.input_tokens
            total_output_tokens += response.usage.output_tokens

            for block in response.content:
                if block.type == "text":
                    final_text += block.text

            final_assistant_msg: anthropic.types.MessageParam = {
                "role": "assistant",
                "content": final_text,
            }
            conversation.append(final_assistant_msg)

        # Record cost for this request
        cost = record_cost(
            tier=router_result.tier,
            model=model,
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens,
        )

        await logger.ainfo(
            "orchestrator_completed",
            session_id=request.session_id,
            model=model,
            tier=router_result.tier.value,
            tokens_input=total_input_tokens,
            tokens_output=total_output_tokens,
            tool_calls_count=tool_calls_count,
            estimated_cost_usd=cost.estimated_cost_usd,
        )

        return OrchestratorResponse(
            session_id=request.session_id,
            response_text=final_text,
            model_used=model,
            tokens_input=total_input_tokens,
            tokens_output=total_output_tokens,
            tool_calls_count=tool_calls_count,
        )

    async def process_message_streaming(
        self,
        request: OrchestratorRequest,
        *,
        on_text_delta: Callable[[str, int], Coroutine[object, object, None]] | None = None,
        on_stream_end: Callable[[str], Coroutine[object, object, None]] | None = None,
        progress_callback: ProgressCallback | None = None,
        host_status: str | None = None,
        user_memories: str | None = None,
    ) -> OrchestratorResponse:
        """Process a user message with streaming text output.

        Tool-calling iterations use non-streaming API calls.
        The final text response is streamed via on_text_delta callback.
        """
        router_result = select_model(request.message)
        model = router_result.model

        await logger.ainfo(
            "orchestrator_streaming_started",
            session_id=request.session_id,
            model=model,
            tier=router_result.tier.value,
        )

        system_prompt = build_system_prompt(
            host_status=host_status,
            user_memories=user_memories,
        )

        conversation = self._get_conversation(request.session_id)
        user_msg: anthropic.types.MessageParam = {
            "role": "user",
            "content": request.message,
        }
        conversation.append(user_msg)

        tools = self._registry.get_tools_for_api()

        total_input_tokens = 0
        total_output_tokens = 0
        tool_calls_count = 0
        final_text = ""

        for iteration in range(MAX_ITERATIONS):
            await logger.ainfo(
                "orchestrator_streaming_iteration",
                session_id=request.session_id,
                iteration=iteration + 1,
            )

            # Non-streaming call to check for tool use
            response = await self._call_claude_api(
                model=model,
                system=system_prompt,
                messages=conversation,
                tools=tools,
            )

            total_input_tokens += response.usage.input_tokens
            total_output_tokens += response.usage.output_tokens

            has_tool_use = False
            tool_result_blocks: list[anthropic.types.ToolResultBlockParam] = []

            for block in response.content:
                if block.type == "tool_use":
                    has_tool_use = True
                    tool_calls_count += 1

                    tool_call = ToolCall(
                        id=block.id,
                        name=block.name,
                        input=dict(block.input),
                    )

                    if progress_callback is not None:
                        await progress_callback(
                            tool_call.name,
                            iteration + 1,
                            MAX_ITERATIONS,
                        )

                    result = await self._execute_tool(tool_call)
                    tool_result_block: anthropic.types.ToolResultBlockParam = {
                        "type": "tool_result",
                        "tool_use_id": result.tool_use_id,
                        "content": result.content,
                        "is_error": result.is_error,
                    }
                    tool_result_blocks.append(tool_result_block)

            if has_tool_use:
                assistant_msg: anthropic.types.MessageParam = {
                    "role": "assistant",
                    "content": response.content,
                }
                conversation.append(assistant_msg)
                tool_user_msg: anthropic.types.MessageParam = {
                    "role": "user",
                    "content": tool_result_blocks,
                }
                conversation.append(tool_user_msg)
            else:
                # Final response — re-issue as streaming
                # Remove the non-streaming response tokens (we'll get new ones)
                total_input_tokens -= response.usage.input_tokens
                total_output_tokens -= response.usage.output_tokens

                delta_index = 0
                async with self._client.messages.stream(
                    model=model,
                    max_tokens=4096,
                    system=system_prompt,
                    messages=conversation,
                ) as stream:
                    async for text in stream.text_stream:
                        final_text += text
                        if on_text_delta is not None:
                            await on_text_delta(text, delta_index)
                        delta_index += 1

                    final_message = await stream.get_final_message()
                    total_input_tokens += final_message.usage.input_tokens
                    total_output_tokens += final_message.usage.output_tokens

                if on_stream_end is not None:
                    await on_stream_end(final_text)

                final_assistant_msg: anthropic.types.MessageParam = {
                    "role": "assistant",
                    "content": final_text,
                }
                conversation.append(final_assistant_msg)
                break
        else:
            await logger.awarning(
                "orchestrator_streaming_max_iterations",
                session_id=request.session_id,
            )
            force_msg: anthropic.types.MessageParam = {
                "role": "user",
                "content": "Maksimum islem limiti asildi. Lutfen son cevabini ver.",
            }
            conversation.append(force_msg)

            delta_index = 0
            async with self._client.messages.stream(
                model=model,
                max_tokens=4096,
                system=system_prompt,
                messages=conversation,
            ) as stream:
                async for text in stream.text_stream:
                    final_text += text
                    if on_text_delta is not None:
                        await on_text_delta(text, delta_index)
                    delta_index += 1

                final_message = await stream.get_final_message()
                total_input_tokens += final_message.usage.input_tokens
                total_output_tokens += final_message.usage.output_tokens

            if on_stream_end is not None:
                await on_stream_end(final_text)

            final_assistant_msg2: anthropic.types.MessageParam = {
                "role": "assistant",
                "content": final_text,
            }
            conversation.append(final_assistant_msg2)

        cost = record_cost(
            tier=router_result.tier,
            model=model,
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens,
        )

        await logger.ainfo(
            "orchestrator_streaming_completed",
            session_id=request.session_id,
            model=model,
            tokens_input=total_input_tokens,
            tokens_output=total_output_tokens,
            tool_calls_count=tool_calls_count,
            estimated_cost_usd=cost.estimated_cost_usd,
        )

        return OrchestratorResponse(
            session_id=request.session_id,
            response_text=final_text,
            model_used=model,
            tokens_input=total_input_tokens,
            tokens_output=total_output_tokens,
            tool_calls_count=tool_calls_count,
        )

    async def _call_claude_api(
        self,
        *,
        model: str,
        system: str,
        messages: Iterable[anthropic.types.MessageParam],
        tools: list[dict[str, object]],
    ) -> anthropic.types.Message:
        """Call Claude API with retry logic for transient errors.

        Implements exponential backoff for 429, 500, 529 errors.

        Args:
            model: Claude model identifier.
            system: System prompt.
            messages: Conversation messages.
            tools: Tool definitions for Claude API.

        Returns:
            Claude API message response.

        Raises:
            ClaudeAPIError: If all retries are exhausted.
        """
        last_error: Exception | None = None

        for attempt in range(_MAX_RETRIES):
            try:
                if tools:
                    return await self._client.messages.create(
                        model=model,
                        max_tokens=4096,
                        system=system,
                        messages=messages,
                        tools=tools,  # type: ignore[arg-type]
                    )
                return await self._client.messages.create(
                    model=model,
                    max_tokens=4096,
                    system=system,
                    messages=messages,
                )

            except anthropic.RateLimitError as exc:
                last_error = exc
                backoff = _RETRY_BACKOFF_SECONDS[min(attempt, len(_RETRY_BACKOFF_SECONDS) - 1)]
                await logger.awarning(
                    "claude_api_rate_limit",
                    attempt=attempt + 1,
                    backoff_seconds=backoff,
                )
                await asyncio.sleep(backoff)

            except anthropic.InternalServerError as exc:
                last_error = exc
                backoff = _RETRY_BACKOFF_SECONDS[min(attempt, len(_RETRY_BACKOFF_SECONDS) - 1)]
                await logger.awarning(
                    "claude_api_server_error",
                    attempt=attempt + 1,
                    backoff_seconds=backoff,
                    status_code=exc.status_code,
                )
                await asyncio.sleep(backoff)

            except anthropic.APIStatusError as exc:
                if exc.status_code == 529:
                    last_error = exc
                    await logger.awarning(
                        "claude_api_overloaded",
                        attempt=attempt + 1,
                    )
                    await asyncio.sleep(10.0)
                else:
                    raise ClaudeAPIError(f"Claude API error: {exc.status_code}") from exc

        error_msg = f"Claude API failed after {_MAX_RETRIES} retries"
        if last_error is not None:
            error_msg += f": {last_error}"
        raise ClaudeAPIError(error_msg)

    async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
        """Execute a tool call and return the result.

        Args:
            tool_call: Tool call from Claude.

        Returns:
            ToolResult with execution output.
        """
        handler = self._registry.get_handler(tool_call.name)

        if handler is None:
            await logger.awarning(
                "tool_not_found",
                tool_name=tool_call.name,
            )
            return ToolResult(
                tool_use_id=tool_call.id,
                content=f"Tool '{tool_call.name}' is not registered.",
                is_error=True,
            )

        # Check approval requirement
        if self._registry.requires_approval(tool_call.name):
            await logger.ainfo(
                "tool_requires_approval",
                tool_name=tool_call.name,
            )
            return ToolResult(
                tool_use_id=tool_call.id,
                content=(
                    f"Tool '{tool_call.name}' requires user approval. "
                    "Approval system not yet connected."
                ),
                is_error=True,
            )

        try:
            await logger.ainfo(
                "tool_executing",
                tool_name=tool_call.name,
                tool_call_id=tool_call.id,
            )
            result_str = await handler(tool_call.input)
            await logger.ainfo(
                "tool_executed",
                tool_name=tool_call.name,
                tool_call_id=tool_call.id,
                success=True,
            )
            return ToolResult(
                tool_use_id=tool_call.id,
                content=result_str,
            )
        except Exception as exc:
            await logger.aexception(
                "tool_execution_failed",
                tool_name=tool_call.name,
                tool_call_id=tool_call.id,
            )
            return ToolResult(
                tool_use_id=tool_call.id,
                content=f"Tool execution failed: {exc}",
                is_error=True,
            )

    def _get_conversation(self, session_id: str) -> list[anthropic.types.MessageParam]:
        """Get or create conversation history for a session.

        Args:
            session_id: Session identifier.

        Returns:
            Conversation message list.
        """
        if session_id not in self._conversations:
            self._conversations[session_id] = []
        return self._conversations[session_id]

    def clear_conversation(self, session_id: str) -> None:
        """Clear conversation history for a session.

        Args:
            session_id: Session identifier.
        """
        self._conversations.pop(session_id, None)

    def _generate_approval_id(self) -> str:
        """Generate a unique approval ID."""
        return str(uuid4())
