"""Claude streaming task manager - callback-based dispatch to Host Agent.

TaskManager'in streaming versiyonu. Future yerine callback pattern kullanir.
Agent'tan gelen claude_stream_* mesajlarini iOS'a yonlendirir.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import structlog

from app.orchestrator.claude_code_runner import (
    ClaudeCodeError,
    ToolProgressEvent,
    ToolStepInfo,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

    from app.core.websocket import ConnectionManager
    from app.services.agent_registry_service import AgentRegistryService

    TextDeltaCallback = Callable[[str, int], Coroutine[object, object, None]]
    ToolProgressCallback = Callable[[ToolProgressEvent], Coroutine[object, object, None]]
    QuestionCallback = Callable[[dict[str, object]], Coroutine[object, object, str | None]]
    StreamEndCallback = Callable[[str], Coroutine[object, object, None]]

logger: structlog.stdlib.BoundLogger = structlog.get_logger()


@dataclass
class ClaudeStreamCallbacks:
    """Callback set for a streaming claude task."""

    on_text_delta: TextDeltaCallback | None = None
    on_tool_progress: ToolProgressCallback | None = None
    on_question: QuestionCallback | None = None
    on_stream_end: StreamEndCallback | None = None


@dataclass
class ClaudeStreamResult:
    """Result data from a completed claude stream."""

    session_id: str = ""
    full_text: str = ""
    model_used: str = ""
    tokens_input: int = 0
    tokens_output: int = 0


@dataclass
class _StreamRecord:
    """Internal tracking for an active streaming task."""

    task_id: str
    host_id: str
    callbacks: ClaudeStreamCallbacks
    completion: asyncio.Future[ClaudeStreamResult]
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))


class ClaudeStreamManager:
    """Manages streaming claude tasks dispatched to Host Agents.

    Unlike TaskManager (Future-based request-response), this uses
    callback-based streaming where each delta/progress/question
    event triggers a callback to forward to iOS.
    """

    def __init__(
        self,
        agent_registry: AgentRegistryService,
        agent_manager: ConnectionManager,
    ) -> None:
        self._registry = agent_registry
        self._manager = agent_manager
        self._streams: dict[str, _StreamRecord] = {}

    async def dispatch(
        self,
        *,
        host_id: str,
        prompt: str,
        session_id: str | None,
        project_dir: str | None,
        append_system_prompt: str | None,
        model: str,
        max_turns: int,
        callbacks: ClaudeStreamCallbacks,
    ) -> str:
        """Dispatch a claude task to an agent. Returns task_id.

        Does NOT block. Caller should await get_completion_future(task_id).
        """
        connection_id = self._registry.get_connection_id(host_id)
        if connection_id is None:
            raise ClaudeCodeError(
                f"Agent '{host_id}' bulunamadi veya offline.",
                returncode=-1,
            )

        task_id = str(uuid4())
        loop = asyncio.get_running_loop()
        completion: asyncio.Future[ClaudeStreamResult] = loop.create_future()

        record = _StreamRecord(
            task_id=task_id,
            host_id=host_id,
            callbacks=callbacks,
            completion=completion,
        )
        self._streams[task_id] = record

        # Build claude_task_execute message
        message: dict[str, object] = {
            "id": str(uuid4()),
            "type": "claude_task_execute",
            "content": {
                "task_id": task_id,
                "prompt": prompt,
                "project_dir": project_dir,
                "session_id": session_id,
                "model": model,
                "max_turns": max_turns,
                "append_system_prompt": append_system_prompt,
            },
            "metadata": {
                "timestamp": datetime.now(tz=UTC).isoformat(),
                "direction": "server_to_agent",
            },
        }

        sent = await self._manager.send_json(connection_id, message)
        if not sent:
            self._streams.pop(task_id, None)
            raise ClaudeCodeError(
                f"Agent '{host_id}' baglantisi kopmus.",
                returncode=-1,
            )

        await logger.ainfo(
            "claude_task_dispatched",
            task_id=task_id,
            host_id=host_id,
            model=model,
        )

        return task_id

    def get_completion_future(self, task_id: str) -> asyncio.Future[ClaudeStreamResult]:
        """Return the future that resolves when stream ends or errors."""
        record = self._streams.get(task_id)
        if record is None:
            raise ValueError(f"Unknown task_id: {task_id}")
        return record.completion

    # ------------------------------------------------------------------
    # Stream event handlers (called from agent_ws.py)
    # ------------------------------------------------------------------

    async def handle_stream_delta(
        self,
        task_id: str,
        delta: str,
        index: int,
    ) -> None:
        """Forward text delta to the iOS callback."""
        record = self._streams.get(task_id)
        if record is None:
            await logger.awarning("claude_stream_delta_unknown_task", task_id=task_id)
            return

        if record.callbacks.on_text_delta is not None:
            await record.callbacks.on_text_delta(delta, index)

    async def handle_stream_progress(
        self,
        task_id: str,
        progress_data: dict[str, Any],
    ) -> None:
        """Forward tool progress to the iOS callback."""
        record = self._streams.get(task_id)
        if record is None:
            return

        if record.callbacks.on_tool_progress is not None:
            # Reconstruct ToolProgressEvent from dict
            steps_raw = progress_data.get("steps", [])
            steps = [
                ToolStepInfo(
                    id=str(s.get("id", "")),
                    step_type=str(s.get("step_type", "")),
                    label=str(s.get("label", "")),
                    status=str(s.get("status", "")),
                    tool_name=s.get("tool_name"),
                    duration_seconds=s.get("duration_seconds"),
                    detail=s.get("detail"),
                )
                for s in steps_raw
                if isinstance(s, dict)
            ]
            event = ToolProgressEvent(
                phase=str(progress_data.get("phase", "")),
                phase_label=str(progress_data.get("phase_label", "")),
                current_tool=progress_data.get("current_tool"),
                percentage=int(progress_data.get("percentage", 0)),
                steps=steps,
            )
            await record.callbacks.on_tool_progress(event)

    async def handle_stream_question(
        self,
        task_id: str,
        question_data: dict[str, Any],
    ) -> None:
        """Forward question to iOS and send answer back to agent."""
        record = self._streams.get(task_id)
        if record is None:
            return

        question_fn = record.callbacks.on_question
        if question_fn is None:
            return

        # Run in background so it doesn't block other stream messages
        async def _ask_and_forward() -> None:
            try:
                answer = await question_fn(question_data)
                if answer:
                    await self.send_question_answer(task_id, answer)
            except Exception:
                await logger.aexception("claude_question_forward_failed", task_id=task_id)

        asyncio.create_task(_ask_and_forward())

    async def handle_stream_end(
        self,
        task_id: str,
        result_data: dict[str, Any],
    ) -> None:
        """Resolve completion future with result data."""
        record = self._streams.pop(task_id, None)
        if record is None:
            return

        result = ClaudeStreamResult(
            session_id=str(result_data.get("session_id", "")),
            full_text=str(result_data.get("full_text", "")),
            model_used=str(result_data.get("model_used", "")),
            tokens_input=int(result_data.get("tokens_input", 0)),
            tokens_output=int(result_data.get("tokens_output", 0)),
        )

        # Call on_stream_end callback
        if record.callbacks.on_stream_end is not None:
            try:
                await record.callbacks.on_stream_end(result.full_text)
            except Exception:
                await logger.aexception("claude_stream_end_callback_failed", task_id=task_id)

        if not record.completion.done():
            record.completion.set_result(result)

        await logger.ainfo(
            "claude_stream_completed",
            task_id=task_id,
            host_id=record.host_id,
            text_length=len(result.full_text),
        )

    async def handle_stream_error(
        self,
        task_id: str,
        error: str,
        returncode: int = -1,
    ) -> None:
        """Resolve completion future with error."""
        record = self._streams.pop(task_id, None)
        if record is None:
            return

        if not record.completion.done():
            record.completion.set_exception(ClaudeCodeError(error, returncode=returncode))

        await logger.awarning(
            "claude_stream_error",
            task_id=task_id,
            host_id=record.host_id,
            error=error,
        )

    async def send_question_answer(self, task_id: str, answer: str) -> None:
        """Send user answer back to the agent."""
        record = self._streams.get(task_id)
        if record is None:
            return

        connection_id = self._registry.get_connection_id(record.host_id)
        if connection_id is None:
            return

        message: dict[str, object] = {
            "id": str(uuid4()),
            "type": "claude_question_answer",
            "content": {
                "task_id": task_id,
                "answer": answer,
            },
            "metadata": {
                "timestamp": datetime.now(tz=UTC).isoformat(),
                "direction": "server_to_agent",
            },
        }
        await self._manager.send_json(connection_id, message)
