"""Orchestrator service - business logic for AI message processing."""

from collections.abc import Callable, Coroutine

import structlog

from app.orchestrator.agent import ClaudeAPIError, MaxIterationsReachedError, OrchestratorAgent
from app.orchestrator.tool_registry import ToolRegistry
from app.schemas.orchestrator import OrchestratorRequest, OrchestratorResponse
from app.tools.cost_tool import CostTool
from app.tools.github_tool import GitHubTool
from app.tools.memory_tool import MemoryTool
from app.tools.s3_tool import S3Tool

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

# Module-level tool registry singleton
_tool_registry: ToolRegistry | None = None


def _register_default_tools(registry: ToolRegistry) -> None:
    """Register all built-in tools with the registry."""
    tools = [
        GitHubTool(),
        MemoryTool(),
        CostTool(),
        S3Tool(),
    ]
    for tool in tools:
        tool.register(registry)
    logger.info("default_tools_registered", count=len(tools))


def get_tool_registry() -> ToolRegistry:
    """Get or create the global tool registry.

    Returns:
        Global ToolRegistry instance.
    """
    global _tool_registry  # noqa: PLW0603
    if _tool_registry is None:
        _tool_registry = ToolRegistry()
        _register_default_tools(_tool_registry)
    return _tool_registry


ProgressCallback = Callable[[str, int, int], Coroutine[object, object, None]]


class OrchestratorService:
    """Service for processing user messages through the AI orchestrator.

    Provides the business logic layer between the WebSocket handler
    and the core OrchestratorAgent.
    """

    def __init__(
        self,
        *,
        tool_registry: ToolRegistry | None = None,
    ) -> None:
        registry = tool_registry or get_tool_registry()
        self._agent = OrchestratorAgent(registry)

    async def process_user_message(
        self,
        *,
        session_id: str,
        user_id: str,
        message: str,
        project_id: str | None = None,
        progress_callback: ProgressCallback | None = None,
        host_status: str | None = None,
        user_memories: str | None = None,
    ) -> OrchestratorResponse:
        """Process a user message and return the AI response.

        Args:
            session_id: WebSocket session ID.
            user_id: Authenticated user ID.
            message: User message text.
            project_id: Optional project context.
            progress_callback: Optional async callback for tool execution progress.
            host_status: Formatted agent status for system prompt.
            user_memories: Formatted user memories for system prompt.

        Returns:
            OrchestratorResponse with AI response text and metadata.
        """
        request = OrchestratorRequest(
            session_id=session_id,
            user_id=user_id,
            message=message,
            project_id=project_id,
        )

        await logger.ainfo(
            "orchestrator_processing",
            session_id=session_id,
            user_id=user_id,
            message_length=len(message),
        )

        try:
            response = await self._agent.process_message(
                request,
                progress_callback=progress_callback,
                host_status=host_status,
                user_memories=user_memories,
            )
            await logger.ainfo(
                "orchestrator_response_generated",
                session_id=session_id,
                model=response.model_used,
                tokens_input=response.tokens_input,
                tokens_output=response.tokens_output,
                tool_calls=response.tool_calls_count,
            )
            return response

        except MaxIterationsReachedError:
            await logger.awarning(
                "orchestrator_max_iterations",
                session_id=session_id,
            )
            return OrchestratorResponse(
                session_id=session_id,
                response_text=(
                    "Islem cok fazla adim gerektirdi. Lutfen daha spesifik bir talep deneyin."
                ),
                model_used="none",
                tokens_input=0,
                tokens_output=0,
                tool_calls_count=0,
            )

        except ClaudeAPIError as exc:
            await logger.aerror(
                "orchestrator_api_error",
                session_id=session_id,
                error=exc.message,
            )
            return OrchestratorResponse(
                session_id=session_id,
                response_text=(
                    "AI servisi gecici olarak kullanilamiyor. Lutfen daha sonra tekrar deneyin."
                ),
                model_used="none",
                tokens_input=0,
                tokens_output=0,
                tool_calls_count=0,
            )

    def clear_session(self, session_id: str) -> None:
        """Clear conversation history for a session.

        Args:
            session_id: Session identifier.
        """
        self._agent.clear_conversation(session_id)
        logger.info("orchestrator_session_cleared", session_id=session_id)
