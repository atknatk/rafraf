"""Claude AI Agent - core orchestrator with tool-calling loop."""

import asyncio
import time
from collections.abc import Callable, Coroutine, Iterable
from uuid import uuid4

import anthropic
import anthropic.types
import structlog

from app.core.config import get_settings
from app.core.metrics import claude_rate_limit_hits_total
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

# Default reset window when Anthropic doesn't supply ``Retry-After`` — the
# RateLimitInfoPayload contract demands a unix timestamp, so we synthesise a
# conservative 5-hour reset matching the Max-plan rolling window so the iOS
# UI degrades gracefully instead of flashing a stale value.
_DEFAULT_RATE_LIMIT_RESET_SECONDS: int = 5 * 60 * 60

# Sentinel ``bridge_id`` label used when the rate-limit hit originated on
# the direct-Anthropic-API fallback path (no bridge involved). Keeps the
# Prometheus counter cardinality bounded.
_API_FALLBACK_BRIDGE_ID: str = "api"

# Type alias for progress callback
ProgressCallback = Callable[[str, int, int], Coroutine[object, object, None]]

# Type alias for the optional rate-limit forwarder. Receives a fully-built
# kwargs dict matching ``ClaudeStreamManager.forward_rate_limit_info``'s
# signature (minus ``user_id`` which is supplied by the caller). Implementing
# the contract this way keeps :class:`OrchestratorAgent` decoupled from
# ``app.services.claude_stream_manager`` (which would create a circular
# import).
RateLimitForwarder = Callable[[str, dict[str, object]], Coroutine[object, object, None]]


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

    def __init__(
        self,
        tool_registry: ToolRegistry,
        *,
        rate_limit_forwarder: RateLimitForwarder | None = None,
    ) -> None:
        self._registry = tool_registry
        settings = get_settings()
        # T1.1: Bedrock branch removed; the bridge owns claude routing now.
        # Backend's API client only handles the legacy fallback path
        # (process_message / process_message_streaming) which calls the
        # Anthropic API directly with the configured API key.
        self._client: anthropic.AsyncAnthropic = anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key,
        )
        # Session-based conversation history
        self._conversations: dict[str, list[anthropic.types.MessageParam]] = {}
        # T2.4: optional forwarder so rate-limit errors raised by the
        # direct-API fallback can still surface ``rate_limit.info`` to the
        # iOS client. ``OrchestratorService`` injects a closure that wraps
        # ``ClaudeStreamManager.forward_rate_limit_info``.
        self._rate_limit_forwarder: RateLimitForwarder | None = rate_limit_forwarder

    def set_rate_limit_forwarder(self, forwarder: RateLimitForwarder | None) -> None:
        """Late-bind a rate-limit forwarder (avoids circular imports at boot).

        ``OrchestratorService`` calls this once it has a
        :class:`ClaudeStreamManager` available; before that, rate-limit hits
        only update the Prometheus counter (no iOS push happens).
        """
        self._rate_limit_forwarder = forwarder

    async def process_message(
        self,
        request: OrchestratorRequest,
        *,
        progress_callback: ProgressCallback | None = None,
        host_status: str | None = None,
    ) -> OrchestratorResponse:
        """Process a user message through the AI orchestrator.

        Runs the tool-calling loop: sends message to Claude, executes
        any tool calls, sends results back, and repeats until Claude
        produces a final text response or max iterations is reached.

        Args:
            request: Orchestrator request with user message.
            progress_callback: Optional async callback for progress updates.
            host_status: Formatted agent status for system prompt.

        Returns:
            OrchestratorResponse with the final AI response.

        Raises:
            MaxIterationsReachedError: If loop exceeds MAX_ITERATIONS.
            ClaudeAPIError: If Claude API returns an unrecoverable error.
        """
        # V1: Single Claude model (subscription tier). No provider routing.
        model = get_settings().claude_default_model

        await logger.ainfo(
            "orchestrator_model_selected",
            session_id=request.session_id,
            model=model,
        )

        # Build system prompt with dynamic context
        system_prompt = build_system_prompt(
            host_status=host_status,
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
                user_id=request.user_id,
                session_id=request.session_id,
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
                user_id=request.user_id,
                session_id=request.session_id,
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

        await logger.ainfo(
            "orchestrator_completed",
            session_id=request.session_id,
            model=model,
            tokens_input=total_input_tokens,
            tokens_output=total_output_tokens,
            tool_calls_count=tool_calls_count,
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
    ) -> OrchestratorResponse:
        """Process a user message with streaming text output.

        Tool-calling iterations use non-streaming API calls.
        The final text response is streamed via on_text_delta callback.
        """
        # V1: Single Claude model (subscription tier). No provider routing.
        model = get_settings().claude_default_model

        await logger.ainfo(
            "orchestrator_streaming_started",
            session_id=request.session_id,
            model=model,
        )

        system_prompt = build_system_prompt(
            host_status=host_status,
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
                user_id=request.user_id,
                session_id=request.session_id,
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

        await logger.ainfo(
            "orchestrator_streaming_completed",
            session_id=request.session_id,
            model=model,
            tokens_input=total_input_tokens,
            tokens_output=total_output_tokens,
            tool_calls_count=tool_calls_count,
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
        user_id: str | None = None,
        session_id: str | None = None,
    ) -> anthropic.types.Message:
        """Call Claude API with retry logic for transient errors.

        Implements exponential backoff for 429, 500, 529 errors. On 429
        ``RateLimitError`` we additionally surface a ``rate_limit.info``
        push to the iOS client (T2.4) and bump the
        ``claude_rate_limit_hits_total`` counter so operators can graph
        the API-fallback path separately from bridge-origin events.

        Args:
            model: Claude model identifier.
            system: System prompt.
            messages: Conversation messages.
            tools: Tool definitions for Claude API.
            user_id: Authenticated user id whose iOS sessions should
                receive the ``rate_limit.info`` push. ``None`` skips the
                forwarder (counter still increments) — matches the legacy
                callers that don't surface rate limits.
            session_id: Active orchestrator session id, attached to the
                push payload so iOS can scope the rate-limit banner.

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
                # T2.4: bump the counter on every observed 429 (not just
                # the terminal one) so operators can see retry pressure.
                claude_rate_limit_hits_total.labels(
                    bridge_id=_API_FALLBACK_BRIDGE_ID,
                    rate_limit_type="five_hour",
                ).inc()
                await self._maybe_forward_rate_limit(
                    exc=exc,
                    user_id=user_id,
                    session_id=session_id,
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

    async def _maybe_forward_rate_limit(
        self,
        *,
        exc: anthropic.RateLimitError,
        user_id: str | None,
        session_id: str | None,
    ) -> None:
        """Push ``rate_limit.info`` to iOS when a forwarder is wired.

        The Anthropic SDK exposes the underlying ``httpx.Response`` on
        ``RateLimitError.response``; we read ``Retry-After`` (seconds or
        an HTTP-date) when present. Missing or unparseable values fall
        back to a 5-hour reset to keep the iOS UI usable.

        The forwarder is best-effort — any exception is logged and
        swallowed so a bridge outage to the iOS connection manager never
        masks the original API error.
        """
        forwarder = self._rate_limit_forwarder
        if forwarder is None or not user_id:
            return

        retry_after_seconds = _parse_retry_after_seconds(exc)
        resets_at = int(time.time()) + (
            retry_after_seconds
            if retry_after_seconds is not None
            else _DEFAULT_RATE_LIMIT_RESET_SECONDS
        )

        payload: dict[str, object] = {
            "session_id": session_id,
            "status": "exceeded",
            "rate_limit_type": "five_hour",
            "resets_at": resets_at,
            "overage_status": "unknown",
            "is_using_overage": False,
        }

        try:
            await forwarder(user_id, payload)
        except Exception:
            await logger.aexception("rate_limit_forwarder_failed")

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


def _parse_retry_after_seconds(exc: anthropic.RateLimitError) -> int | None:
    """Extract a non-negative seconds value from a 429's ``Retry-After`` header.

    Anthropic only ever sends an integer-seconds form today, but RFC 7231
    allows an HTTP-date — we accept either and fall back to ``None`` for
    anything we can't parse so :meth:`OrchestratorAgent._maybe_forward_rate_limit`
    can substitute a default reset window.

    Best-effort: any unexpected attribute or parse error returns ``None``
    (the caller treats that as "use the default 5h window").
    """
    response = getattr(exc, "response", None)
    if response is None:
        return None
    headers = getattr(response, "headers", None)
    if headers is None:
        return None
    raw = headers.get("retry-after")
    if raw is None:
        return None
    raw = str(raw).strip()
    if not raw:
        return None
    try:
        seconds = int(raw)
    except ValueError:
        # HTTP-date form. Fall back to None — the iOS UI will still show a
        # reasonable banner using the synthesised default.
        try:
            from email.utils import parsedate_to_datetime

            target = parsedate_to_datetime(raw)
            delta = int(target.timestamp() - time.time())
        except (TypeError, ValueError):
            return None
        return max(delta, 0)
    return max(seconds, 0)
