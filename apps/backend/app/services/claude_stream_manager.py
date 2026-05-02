"""Claude streaming task manager - callback-based dispatch to Host Agent.

TaskManager'in streaming versiyonu. Future yerine callback pattern kullanir.
Agent'tan gelen claude_stream_* mesajlarini iOS'a yonlendirir.

T1.2 additions (Faz 1 — Agent Teams):
    Eight ``forward_*`` methods that wrap each new bridge event into a typed
    Pydantic payload (``app.schemas.messages``) + envelope dict and push it
    to the relevant iOS WebSocket session(s). Each forwarder is invoked by
    a closure registered against the matching ClaudeCodeRunner v2 callback
    (``on_session_init``, ``on_subagent_*``, ``on_rate_limit``) — and, for
    the statusline-driven ``usage.report``, by the bridge-event hook in
    :mod:`app.api.routes.agent_ws`.

    Server-side timestamp injection (T1.5 reviewer M3): ``session.title``
    + ``session.pr_opened`` payloads acquire ``generated_at`` /
    ``opened_at`` here when the bridge envelope omits them — matching the
    same defensive injection ClaudeCodeRunner does for session/subagent
    events (idempotent — does not overwrite a real value).

    UUID coercion (T1.5 reviewer M1): ``SessionTitlePayload`` and
    ``SessionPrOpenedPayload`` require ``session_id: UUID`` even though
    the runner surfaces it as a ``str``; the forwarder casts.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

import structlog

from app.core import metrics as _metrics
from app.orchestrator.claude_code_runner import (
    ClaudeCodeError,
    ToolProgressEvent,
    ToolStepInfo,
)
from app.schemas.messages import (
    MessageDirection,
    MessageType,
    RateLimitInfoPayload,
    SessionInitPayload,
    SessionPrOpenedPayload,
    SessionTitlePayload,
    SubagentCompletedPayload,
    SubagentProgressPayload,
    SubagentSpawnedPayload,
    UsageReportPayload,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

    from app.core.websocket import ConnectionManager
    from app.services.bridge_registry_service import BridgeRegistryService

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
        agent_registry: BridgeRegistryService,
        agent_manager: ConnectionManager,
        ios_manager: ConnectionManager | None = None,
    ) -> None:
        self._registry = agent_registry
        self._manager = agent_manager
        # iOS-side ConnectionManager (separate from the bridge-side one).
        # Optional so existing constructor call sites — and the legacy
        # ``dispatch`` / ``handle_*`` flow — keep working without it. When
        # ``None``, the ``forward_*`` methods log + skip the push instead of
        # crashing; callers wanting iOS forwarding (T1.2 Agent Teams) MUST
        # pass it (``agent_ws.get_claude_stream_manager`` does).
        self._ios_manager: ConnectionManager | None = ios_manager
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

    # ------------------------------------------------------------------
    # Agent Teams forwarders (T1.2) — bridge → iOS push.
    #
    # Each method:
    #   1. Validates / coerces the bridge payload into the matching
    #      Pydantic schema (T1.5).
    #   2. Wraps it in a server-to-client envelope dict.
    #   3. Sends it to every iOS connection of ``user_id`` via
    #      ``ios_manager.send_to_user``.
    #
    # ``user_id`` is the iOS-side user UUID (string OK — both
    # ``ConnectionManager.send_to_user`` and the on-the-wire metadata field
    # accept the str form).
    # ------------------------------------------------------------------

    async def forward_session_init(
        self,
        *,
        user_id: str,
        session_id: str,
        model: str,
        permission_mode: str,
        api_key_source: str,
        cwd: str,
        agent_teams_enabled: bool,
        initialized_at: datetime | None = None,
    ) -> int:
        """Push ``session.init`` to all iOS sessions of ``user_id``."""
        payload = SessionInitPayload(
            session_id=session_id,
            model=model,
            permission_mode=permission_mode,
            api_key_source=api_key_source,
            cwd=cwd,
            agent_teams_enabled=agent_teams_enabled,
            initialized_at=initialized_at or datetime.now(tz=UTC),
        )
        return await self._push_typed_to_user(
            user_id=user_id,
            msg_type=MessageType.SESSION_INIT,
            payload=payload.model_dump(mode="json"),
            session_id=session_id,
        )

    async def forward_subagent_spawned(
        self,
        *,
        user_id: str,
        session_id: str | None,
        task_id: str,
        name: str,
        description: str | None = None,
        prompt_preview: str,
        subagent_type: str | None = None,
        isolation: str | None = None,
        started_at: datetime | None = None,
    ) -> int:
        """Push ``subagent.spawned`` to all iOS sessions of ``user_id``."""
        payload = SubagentSpawnedPayload(
            task_id=task_id,
            name=name,
            description=description,
            prompt_preview=prompt_preview,
            subagent_type=subagent_type,
            isolation=isolation,
            started_at=started_at or datetime.now(tz=UTC),
        )
        return await self._push_typed_to_user(
            user_id=user_id,
            msg_type=MessageType.SUBAGENT_SPAWNED,
            payload=payload.model_dump(mode="json"),
            session_id=session_id,
        )

    async def forward_subagent_progress(
        self,
        *,
        user_id: str,
        session_id: str | None,
        task_id: str,
        status: str,
        activity: str,
        updated_at: datetime | None = None,
    ) -> int:
        """Push ``subagent.progress`` to all iOS sessions of ``user_id``."""
        payload = SubagentProgressPayload(
            task_id=task_id,
            status=status,
            activity=activity,
            updated_at=updated_at or datetime.now(tz=UTC),
        )
        return await self._push_typed_to_user(
            user_id=user_id,
            msg_type=MessageType.SUBAGENT_PROGRESS,
            payload=payload.model_dump(mode="json"),
            session_id=session_id,
        )

    async def forward_subagent_completed(
        self,
        *,
        user_id: str,
        session_id: str | None,
        task_id: str,
        status: str,
        summary: str | None = None,
        total_tokens: int,
        tool_uses: int,
        duration_ms: int,
        completed_at: datetime | None = None,
    ) -> int:
        """Push ``subagent.completed`` to all iOS sessions of ``user_id``."""
        payload = SubagentCompletedPayload(
            task_id=task_id,
            status=status,
            summary=summary,
            total_tokens=total_tokens,
            tool_uses=tool_uses,
            duration_ms=duration_ms,
            completed_at=completed_at or datetime.now(tz=UTC),
        )
        return await self._push_typed_to_user(
            user_id=user_id,
            msg_type=MessageType.SUBAGENT_COMPLETED,
            payload=payload.model_dump(mode="json"),
            session_id=session_id,
        )

    async def forward_rate_limit_info(
        self,
        *,
        user_id: str,
        session_id: str | None,
        status: str,
        rate_limit_type: str,
        resets_at: int,
        overage_status: str,
        is_using_overage: bool,
    ) -> int:
        """Push ``rate_limit.info`` to all iOS sessions of ``user_id``."""
        payload = RateLimitInfoPayload(
            status=status,
            rate_limit_type=rate_limit_type,
            resets_at=resets_at,
            overage_status=overage_status,
            is_using_overage=is_using_overage,
        )
        return await self._push_typed_to_user(
            user_id=user_id,
            msg_type=MessageType.RATE_LIMIT_INFO,
            payload=payload.model_dump(mode="json"),
            session_id=session_id,
        )

    async def forward_session_title(
        self,
        *,
        user_id: str,
        session_id: str | UUID,
        ai_title: str,
        generated_at: datetime | None = None,
    ) -> int:
        """Push ``session.title`` to all iOS sessions of ``user_id``.

        ``session_id`` is coerced to ``UUID`` per T1.5 reviewer M1.
        ``generated_at`` is server-side-injected when omitted (T1.5 M3).
        """
        sid = session_id if isinstance(session_id, UUID) else UUID(session_id)
        payload = SessionTitlePayload(
            session_id=sid,
            ai_title=ai_title,
            generated_at=generated_at or datetime.now(tz=UTC),
        )
        return await self._push_typed_to_user(
            user_id=user_id,
            msg_type=MessageType.SESSION_TITLE,
            payload=payload.model_dump(mode="json"),
            session_id=str(sid),
        )

    async def forward_session_pr_opened(
        self,
        *,
        user_id: str,
        session_id: str | UUID,
        pr_number: int,
        pr_url: str,
        pr_repository: str,
        opened_at: datetime | None = None,
    ) -> int:
        """Push ``session.pr_opened`` to all iOS sessions of ``user_id``.

        ``session_id`` is coerced to ``UUID`` per T1.5 reviewer M1.
        ``opened_at`` is server-side-injected when omitted (T1.5 M3).
        """
        sid = session_id if isinstance(session_id, UUID) else UUID(session_id)
        payload = SessionPrOpenedPayload(
            session_id=sid,
            pr_number=pr_number,
            pr_url=pr_url,
            pr_repository=pr_repository,
            opened_at=opened_at or datetime.now(tz=UTC),
        )
        return await self._push_typed_to_user(
            user_id=user_id,
            msg_type=MessageType.SESSION_PR_OPENED,
            payload=payload.model_dump(mode="json"),
            session_id=str(sid),
        )

    async def forward_usage_report(
        self,
        *,
        user_id: str,
        five_hour_pct: int,
        seven_day_pct: int,
        five_hour_resets_at: int,
        seven_day_resets_at: int,
        reported_at: int,
        bridge_id: str | None = None,
    ) -> int:
        """Push ``usage.report`` to ALL iOS sessions of ``user_id``.

        Multicast: subscription usage is user-wide (not session-scoped) so
        every active iOS connection of the user must receive the payload.
        Returns the number of connections the message was successfully
        delivered to.

        T2.2: bumps :data:`claude_usage_report_total` and updates the
        per-user gauges (``claude_5h_usage_pct`` / ``claude_7d_usage_pct``
        / ``claude_usage_report_age_seconds``). ``bridge_id`` is optional
        so legacy callers that don't have it still work — defaults to
        ``"unknown"`` for the counter label.
        """
        payload = UsageReportPayload(
            five_hour_pct=five_hour_pct,
            seven_day_pct=seven_day_pct,
            five_hour_resets_at=five_hour_resets_at,
            seven_day_resets_at=seven_day_resets_at,
            reported_at=reported_at,
        )
        # Update gauges before forwarding so a delivery failure still
        # surfaces the latest known usage.
        _metrics.claude_5h_usage_pct.labels(user_id=user_id).set(float(five_hour_pct))
        _metrics.claude_7d_usage_pct.labels(user_id=user_id).set(float(seven_day_pct))
        # ``reported_at`` is a Unix-epoch seconds timestamp on the wire;
        # the staleness gauge surfaces "how long ago" without requiring
        # a separate scrape.
        now_epoch_sec = datetime.now(tz=UTC).timestamp()
        age_sec = max(0.0, now_epoch_sec - float(reported_at))
        _metrics.claude_usage_report_age_seconds.labels(user_id=user_id).set(age_sec)

        _metrics.claude_usage_report_total.labels(
            bridge_id=bridge_id or "unknown",
        ).inc()
        return await self._push_typed_to_user(
            user_id=user_id,
            msg_type=MessageType.USAGE_REPORT,
            payload=payload.model_dump(mode="json"),
            session_id=None,
        )

    async def _push_typed_to_user(
        self,
        *,
        user_id: str,
        msg_type: MessageType,
        payload: dict[str, object],
        session_id: str | None,
    ) -> int:
        """Build a server-to-client envelope dict and broadcast to a user.

        Returns the number of connections the message reached (0 when no
        iOS manager is wired or the user has no active connections).
        """
        if self._ios_manager is None:
            await logger.adebug(
                "claude_stream_forwarder_no_ios_manager",
                msg_type=msg_type.value,
                user_id=user_id,
            )
            return 0
        envelope: dict[str, object] = {
            "id": str(uuid4()),
            "type": msg_type.value,
            "content": payload,
            "metadata": {
                "timestamp": datetime.now(tz=UTC).isoformat(),
                "session_id": session_id,
                "direction": MessageDirection.SERVER_TO_CLIENT.value,
            },
        }
        sent: int = await self._ios_manager.send_to_user(user_id, envelope)
        await logger.adebug(
            "claude_stream_forwarded",
            msg_type=msg_type.value,
            user_id=user_id,
            sessions_reached=sent,
        )
        return sent
