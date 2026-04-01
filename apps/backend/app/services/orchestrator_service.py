"""Orchestrator service - business logic for AI message processing."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Coroutine

import structlog

from app.orchestrator.agent import ClaudeAPIError, MaxIterationsReachedError, OrchestratorAgent
from app.orchestrator.claude_code_runner import (
    ClaudeCodeError,
    ToolProgressCallback,
)
from app.orchestrator.tool_registry import ToolRegistry
from app.schemas.orchestrator import OrchestratorRequest, OrchestratorResponse
from app.services.memory_service import MemoryServiceError, memory_service
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

    async def process_user_message_streaming(
        self,
        *,
        session_id: str,
        user_id: str,
        message: str,
        on_text_delta: Callable[[str, int], Coroutine[object, object, None]] | None = None,
        on_stream_end: Callable[[str], Coroutine[object, object, None]] | None = None,
        project_id: str | None = None,
        progress_callback: ProgressCallback | None = None,
        host_status: str | None = None,
        user_memories: str | None = None,
    ) -> OrchestratorResponse:
        """Process a user message with streaming text output.

        Streams text deltas via on_text_delta callback as Claude generates tokens.
        """
        request = OrchestratorRequest(
            session_id=session_id,
            user_id=user_id,
            message=message,
            project_id=project_id,
        )

        await logger.ainfo(
            "orchestrator_streaming_processing",
            session_id=session_id,
            user_id=user_id,
            message_length=len(message),
        )

        try:
            response = await self._agent.process_message_streaming(
                request,
                on_text_delta=on_text_delta,
                on_stream_end=on_stream_end,
                progress_callback=progress_callback,
                host_status=host_status,
                user_memories=user_memories,
            )
            await logger.ainfo(
                "orchestrator_streaming_response_generated",
                session_id=session_id,
                model=response.model_used,
                tokens_input=response.tokens_input,
                tokens_output=response.tokens_output,
            )
            return response

        except MaxIterationsReachedError:
            await logger.awarning(
                "orchestrator_streaming_max_iterations",
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
                "orchestrator_streaming_api_error",
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

    async def _build_memory_context(
        self,
        user_id: str,
        message: str,
        project_id: str | None,
    ) -> str:
        """Build memory context string from 3-layer memory system.

        Silently returns empty string on failure to avoid blocking AI responses.
        """
        try:
            import json

            from app.core.database import async_session_factory
            from app.repositories.memory_repository import MemoryRepository

            project_uuid = uuid.UUID(project_id) if project_id else None
            async with async_session_factory() as _mem_db:
                repo = MemoryRepository(_mem_db)
                context = await memory_service.get_context_for_message(
                    repo=repo,
                    user_id=user_id,
                    message=message,
                    project_id=project_uuid,
                )
            parts: list[str] = []
            if context.personal_memories:
                items = "\n".join(f"- {m}" for m in context.personal_memories)
                parts.append(f"Kisisel hafiza:\n{items}")
            if context.project_summary:
                summary = json.dumps(context.project_summary, ensure_ascii=False)
                parts.append(f"Proje hafizasi:\n{summary}")
            if context.conversation_summary:
                parts.append("Konusma ozeti:\n" + context.conversation_summary)
            if not parts:
                return ""
            return "\n\n## Hafiza Baglami\n" + "\n\n".join(parts)
        except (MemoryServiceError, Exception):
            await logger.awarning(
                "memory_context_build_failed",
                user_id=user_id,
                project_id=project_id,
            )
            return ""

    async def process_with_claude_code(
        self,
        *,
        session_id: str,
        user_id: str,
        message: str,
        project_id: str | None = None,
        db_session: object | None = None,
        claude_session_id: str | None = None,
        on_text_delta: Callable[[str, int], Coroutine[object, object, None]] | None = None,
        on_stream_end: Callable[[str], Coroutine[object, object, None]] | None = None,
        on_tool_progress: ToolProgressCallback | None = None,
        on_question: (
            Callable[[dict[str, object]], Coroutine[object, object, str | None]] | None
        ) = None,
    ) -> OrchestratorResponse:
        """Process a user message via claude -p subprocess.

        Primary execution path. Falls back to API if claude -p fails
        and fallback is enabled in config.

        Args:
            session_id: WebSocket session ID.
            user_id: Authenticated user ID.
            message: User message text.
            project_id: Optional project ID for scoped sessions and memory.
            db_session: Optional AsyncSession for project local_path lookup.
            claude_session_id: Previous claude -p session ID for --resume.
            on_text_delta: Streaming text callback.
            on_stream_end: Stream completion callback.
            on_tool_progress: Tool usage progress callback.
            on_question: Question forwarding callback.

        Returns:
            OrchestratorResponse with AI response.
        """
        from app.core.config import get_settings

        settings = get_settings()

        await logger.ainfo(
            "claude_code_processing",
            session_id=session_id,
            user_id=user_id,
            message_length=len(message),
            project_id=project_id,
        )

        # Build project-scoped session key
        session_key = f"{session_id}:project:{project_id}" if project_id else session_id

        # Lookup previous claude session for conversation continuation
        if claude_session_id is None:
            claude_session_id = await self._get_claude_session(session_key)

        # Rotate session every 40 messages (~20 turns) to avoid context window overflow
        if project_id and db_session and claude_session_id:
            msg_count = await self._get_project_message_count(project_id, db_session)
            if msg_count > 0 and msg_count % 40 == 0:
                claude_session_id = None
                await self._clear_claude_session(session_key)
                await logger.ainfo(
                    "claude_session_rotated",
                    session_key=session_key,
                    project_id=project_id,
                    msg_count=msg_count,
                )

        # Resolve project local path for claude -p working directory
        project_local_path: str | None = None
        if project_id and db_session is not None:
            project_local_path = await self._get_project_local_path(project_id, db_session)
        if not project_local_path:
            project_local_path = settings.claude_code_default_dir or None

        # Build git context for project awareness
        git_ctx = ""
        if project_local_path:
            from app.services.git_context_service import build_git_context

            git_ctx = await build_git_context(project_local_path)

        # Build memory context from 3-layer memory system
        memory_ctx = await self._build_memory_context(user_id, message, project_id)

        # When starting a fresh session after rotation, inject recent conversation context
        recent_ctx = ""
        if claude_session_id is None and project_id and db_session:
            recent_ctx = await self._build_recent_context(project_id, db_session)

        # Build context info for system prompt
        context_parts: list[str] = [
            f"WebSocket Session: {session_id}",
            f"User ID: {user_id}",
        ]
        if project_id:
            context_parts.append(f"Project ID: {project_id}")
        if project_local_path:
            context_parts.append(f"Project Directory: {project_local_path}")
        if git_ctx:
            context_parts.append(git_ctx)
        if memory_ctx:
            context_parts.append(memory_ctx)
        if recent_ctx:
            context_parts.append(recent_ctx)
        append_prompt = "\n".join(context_parts)

        try:
            import asyncio

            from app.api.routes.agent_ws import get_claude_stream_manager
            from app.api.routes.agent_ws import agent_registry as _ws_agent_registry
            from app.services.agent_registry_service import agent_registry
            from app.services.claude_stream_manager import ClaudeStreamCallbacks

            # Resolve agent: prefer project-linked agent, fallback to any online
            host_id = await self._resolve_agent_for_project(project_id, db_session)
            if host_id is None:
                # Debug: log registry state from both sources
                agents_list = agent_registry.list_agents_sync()
                ws_agents_list = _ws_agent_registry.list_agents_sync() if _ws_agent_registry is not agent_registry else []
                await logger.aerror(
                    "claude_code_no_agent_found",
                    registry_agents=len(agents_list),
                    registry_id=id(agent_registry),
                    ws_registry_agents=len(ws_agents_list),
                    ws_registry_id=id(_ws_agent_registry),
                    same_instance=(agent_registry is _ws_agent_registry),
                    agents_detail=[
                        {"host_id": a["host_id"], "status": str(a["status"])}
                        for a in agents_list
                    ],
                    ws_agents_detail=[
                        {"host_id": a["host_id"], "status": str(a["status"])}
                        for a in ws_agents_list
                    ],
                    project_id=project_id,
                )
                raise ClaudeCodeError(
                    "Uygun agent bulunamadi. Agent'in online oldugundan emin olun.",
                    returncode=-1,
                )

            csm = get_claude_stream_manager()
            callbacks = ClaudeStreamCallbacks(
                on_text_delta=on_text_delta,
                on_tool_progress=on_tool_progress,
                on_question=on_question,
                on_stream_end=on_stream_end,
            )

            task_id = await csm.dispatch(
                host_id=host_id,
                prompt=message,
                session_id=claude_session_id,
                project_dir=project_local_path,
                append_system_prompt=append_prompt,
                model=settings.claude_code_model,
                max_turns=settings.claude_code_max_turns,
                callbacks=callbacks,
            )

            # Wait for stream completion
            completion_future = csm.get_completion_future(task_id)
            try:
                result = await asyncio.wait_for(
                    completion_future,
                    timeout=settings.claude_code_timeout_seconds,
                )
            except TimeoutError:
                # Clean up the stream record on timeout
                await csm.handle_stream_error(task_id, "Timeout bekleme suresi asimi", -1)
                raise ClaudeCodeError(
                    f"claude -p timed out after {settings.claude_code_timeout_seconds}s",
                    returncode=-1,
                ) from None

            await logger.ainfo(
                "claude_code_response_generated",
                session_id=session_id,
                claude_session_id=result.session_id,
                model=result.model_used,
                text_length=len(result.full_text),
                agent_host_id=host_id,
            )

            # Save session after successful execution (project-scoped key)
            if result.session_id:
                await self._save_claude_session(session_key, result.session_id)

            # Track subscription usage
            try:
                from app.services.subscription_usage_service import (
                    subscription_usage_service,
                )

                await subscription_usage_service.record_message()
            except Exception:
                pass  # Non-critical

            return OrchestratorResponse(
                session_id=session_id,
                response_text=result.full_text,
                model_used=f"claude-code:{result.model_used}",
                tokens_input=result.tokens_input,
                tokens_output=result.tokens_output,
                tool_calls_count=0,
            )

        except ClaudeCodeError as exc:
            await logger.aerror(
                "claude_code_failed",
                session_id=session_id,
                error=exc.message,
                returncode=exc.returncode,
            )

            # Fallback to API if enabled
            if settings.claude_code_fallback_to_api:
                await logger.ainfo(
                    "claude_code_fallback_to_api",
                    session_id=session_id,
                )
                return await self.process_user_message_streaming(
                    session_id=session_id,
                    user_id=user_id,
                    message=message,
                    on_text_delta=on_text_delta,
                    on_stream_end=on_stream_end,
                )

            return OrchestratorResponse(
                session_id=session_id,
                response_text="AI servisi gecici olarak kullanilamiyor. Lutfen tekrar deneyin.",
                model_used="none",
                tokens_input=0,
                tokens_output=0,
                tool_calls_count=0,
            )

    async def _resolve_agent_for_project(
        self,
        project_id: str | None,
        db_session: object | None,
    ) -> str | None:
        """Find a suitable online agent for the given project.

        Priority:
        1. Agent linked to the project (via AgentProjectService)
        2. Any online agent with claude_code capability
        """
        # Import from agent_ws to ensure we use the same registry instance
        # that receives agent registrations via WebSocket
        from app.api.routes.agent_ws import agent_registry

        if project_id and db_session is not None:
            try:
                from sqlalchemy import select

                from app.models.agent_project import AgentProject

                result = await db_session.execute(
                    select(AgentProject.agent_id).where(
                        AgentProject.project_id == uuid.UUID(project_id),
                        AgentProject.is_active.is_(True),
                    )
                )
                agent_ids = [row[0] for row in result.all()]
                # Check which are online
                for agent_id in agent_ids:
                    conn_id = agent_registry.get_connection_id(agent_id)
                    if conn_id is not None:
                        return agent_id
            except Exception:
                await logger.awarning(
                    "agent_resolve_project_fallback",
                    project_id=project_id,
                )

        # Fallback: any online agent with claude_code capability
        return agent_registry.find_online_agent_with_capability("claude_code")

    async def _clear_claude_session(self, ws_session_id: str) -> None:
        """Remove saved claude -p session ID from Redis (forces fresh session on next call)."""
        import redis.asyncio as redis

        from app.core.config import get_settings

        settings = get_settings()
        r = redis.from_url(settings.redis_url)
        await r.delete(f"claude_session:{ws_session_id}")
        await r.aclose()

    @staticmethod
    async def _get_project_message_count(project_id: str, db_session: object) -> int:
        """Count messages for a project to decide session rotation."""
        try:
            from sqlalchemy import func, select
            from sqlalchemy.ext.asyncio import AsyncSession

            from app.models.message import Message

            if not isinstance(db_session, AsyncSession):
                return 0
            result = await db_session.execute(
                select(func.count()).select_from(Message).where(
                    Message.project_id == uuid.UUID(project_id)
                )
            )
            return int(result.scalar() or 0)
        except Exception:
            await logger.awarning("message_count_failed", project_id=project_id)
            return 0

    @staticmethod
    async def _build_recent_context(project_id: str, db_session: object) -> str:
        """Build a brief recent conversation summary for fresh session injection."""
        try:
            from sqlalchemy.ext.asyncio import AsyncSession

            from app.services.conversation_service import ConversationService

            if not isinstance(db_session, AsyncSession):
                return ""
            recent = await ConversationService(db_session).get_history(
                project_id=uuid.UUID(project_id), limit=6
            )
            if not recent.messages:
                return ""
            lines = [f"{m.role}: {m.content[:200]}" for m in recent.messages]
            return "\n## Son Konuşmadan Bağlam\n" + "\n".join(lines)
        except Exception:
            await logger.awarning("recent_context_build_failed", project_id=project_id)
            return ""

    async def _save_claude_session(self, ws_session_id: str, claude_session_id: str) -> None:
        """Save claude -p session ID to Redis for session continuation."""
        import redis.asyncio as redis

        from app.core.config import get_settings

        settings = get_settings()
        r = redis.from_url(settings.redis_url)
        await r.set(
            f"claude_session:{ws_session_id}",
            claude_session_id,
            ex=86400,  # 24 hours TTL
        )
        await r.aclose()

    async def _get_claude_session(self, ws_session_id: str) -> str | None:
        """Get saved claude -p session ID from Redis."""
        import redis.asyncio as redis

        from app.core.config import get_settings

        settings = get_settings()
        r = redis.from_url(settings.redis_url)
        result = await r.get(f"claude_session:{ws_session_id}")
        await r.aclose()
        if isinstance(result, bytes):
            return result.decode("utf-8")
        return None

    @staticmethod
    async def _get_project_local_path(project_id: str, db_session: object) -> str | None:
        """Proje local_path'ini DB'den getirir. Hata durumunda None dondurur."""
        try:
            import uuid

            from sqlalchemy.ext.asyncio import AsyncSession

            from app.repositories.project_repo import ProjectRepository

            if not isinstance(db_session, AsyncSession):
                return None
            repo = ProjectRepository(db_session)
            project = await repo.get_by_id(uuid.UUID(project_id))
            return project.local_path if project else None
        except Exception:
            await logger.awarning("project_local_path_lookup_failed", project_id=project_id)
            return None

    def clear_session(self, session_id: str) -> None:
        """Clear conversation history for a session.

        Args:
            session_id: Session identifier.
        """
        self._agent.clear_conversation(session_id)
        logger.info("orchestrator_session_cleared", session_id=session_id)
