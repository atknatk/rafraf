"""Claude Code runner — RPC adapter that forwards work to a Mac Go bridge.

v2.0 (Faz 1 / T1.1):
    The legacy v1 implementation spawned `claude -p` directly inside the
    backend container. As of the Production Pivot Spec (docs/10
    §6.1.1), claude execution lives **only** on a Mac/Linux Go bridge
    (`apps/rafraf-bridge/internal/claude/runner.go`). The backend is now a
    pure orchestrator: it picks a target bridge, sends a
    ``command.claude.run`` RPC envelope over the bridge's WebSocket, and
    consumes the typed event stream the bridge emits.

The 8 ``event.session.*`` envelopes the bridge produces (per docs/10
§6.1.2) are dispatched to a small set of optional async callbacks that
mirror the v1 surface so existing call sites (``claude_stream_manager.py``,
``websocket.py``, ``orchestrator_service.py``) keep working without
changes. The two new callbacks (``on_session_init``, ``on_subagent_*``,
``on_rate_limit``) are added as keyword-only optionals so legacy callers
that don't supply them are unaffected.

Public types preserved for backwards compatibility:
    * :class:`ClaudeCodeError` — raised on RPC/transport failures.
    * :class:`ClaudeCodeResult` — final result aggregated from
      ``event.session.result`` (cost + permission denials populated).
    * :class:`ToolStepInfo` / :class:`ToolProgressEvent` — unchanged shape
      so iOS progress UI keeps rendering.
    * Callback type aliases (``TextDeltaCallback`` etc.) — unchanged.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncIterator, Callable, Coroutine
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import structlog
from opentelemetry import trace

from app.core import metrics as _metrics
from app.core.telemetry import get_tracer

if TYPE_CHECKING:
    from app.repositories.session_repo import SessionRepository
    from app.repositories.subagent_repo import SubagentRepository
    from app.schemas.approval import ApprovalRequestRecord
    from app.services.bridge_registry_service import BridgeRegistryService

logger: structlog.stdlib.BoundLogger = structlog.get_logger()
tracer = get_tracer(__name__)


_TOOL_DISPLAY_NAMES: dict[str, str] = {
    "Read": "Dosya okunuyor",
    "Write": "Dosya yazılıyor",
    "Edit": "Dosya düzenleniyor",
    "MultiEdit": "Çoklu düzenleme",
    "Bash": "Komut çalıştırılıyor",
    "Glob": "Dosya aranıyor",
    "Grep": "İçerik aranıyor",
    "LS": "Dizin listeleniyor",
    "TodoWrite": "Görev listesi güncelleniyor",
    "WebFetch": "Web sayfası getiriliyor",
    "WebSearch": "Web araması yapılıyor",
    "Agent": "Alt görev çalıştırılıyor",
    "NotebookEdit": "Notebook düzenleniyor",
    "AskUserQuestion": "Kullanıcıya soru soruluyor",
    "SendMessage": "Mesaj gönderiliyor",
}


def _tool_display_name(tool_name: str) -> str:
    """Return Turkish display name for a Claude tool, or raw name as fallback."""
    return _TOOL_DISPLAY_NAMES.get(tool_name, tool_name)


@dataclass(frozen=True)
class ToolStepInfo:
    """Single step in the execution timeline."""

    id: str
    step_type: str  # "thinking", "tool_calling", "generating"
    label: str
    status: str  # "pending", "active", "completed", "failed"
    tool_name: str | None = None
    duration_seconds: float | None = None
    detail: str | None = None


@dataclass(frozen=True)
class ToolProgressEvent:
    """Rich progress event sent to WebSocket handler."""

    phase: str  # "starting", "thinking", "tool_calling", "generating", "completed"
    phase_label: str
    current_tool: str | None
    percentage: int
    steps: list[ToolStepInfo]


# Callback type aliases (preserved for callers).
TextDeltaCallback = Callable[[str, int], Coroutine[object, object, None]]
ToolProgressCallback = Callable[[ToolProgressEvent], Coroutine[object, object, None]]
QuestionCallback = Callable[[dict[str, object]], Coroutine[object, object, str | None]]
StreamEndCallback = Callable[[str], Coroutine[object, object, None]]

# v2.0 callbacks (optional). Caller may pass dict payloads as-is —
# typed Pydantic decoding belongs to the forwarder (T1.2).
SessionInitCallback = Callable[[dict[str, object]], Coroutine[object, object, None]]
SubagentSpawnedCallback = Callable[[dict[str, object]], Coroutine[object, object, None]]
SubagentProgressCallback = Callable[[dict[str, object]], Coroutine[object, object, None]]
SubagentCompletedCallback = Callable[[dict[str, object]], Coroutine[object, object, None]]
RateLimitCallback = Callable[[dict[str, object]], Coroutine[object, object, None]]

# V1.4 — bridge ``event.session.permission_request`` callback.
# Receives the freshly-created :class:`ApprovalRequestRecord` plus the
# routing trio (bridge_host_id, rpc_id, timeout_seconds) the awaiter
# needs to dispatch the eventual ``command.claude.permission.{allow,
# deny}`` envelope back. The runner stays pure event-dispatch — the
# callback owns the iOS push + decision-await + bridge-reply round-trip
# and MUST be fire-and-forget so the runner's stream loop is never
# blocked by user think-time. See design doc V1.4 §2.1.4 + §2.2.3.
PermissionRequestCallback = Callable[
    ["ApprovalRequestRecord", str, str, int],
    Coroutine[object, object, None],
]


@dataclass(frozen=True)
class ClaudeCodeResult:
    """Result from a claude RPC run.

    ``response_text`` is populated from ``event.session.result.result``;
    other terminal fields originate from the same envelope. Cache token
    fields are surfaced in addition to the legacy input/output buckets so
    callers (T2.5 cost summary) can reason about Anthropic prompt caching
    separately — cache READ is an order of magnitude cheaper than fresh
    INPUT, so collapsing them would inflate the projected spend.
    """

    session_id: str
    response_text: str
    model_used: str
    duration_ms: int
    is_error: bool
    tokens_input: int = 0
    tokens_output: int = 0
    tokens_cache_creation: int = 0
    tokens_cache_read: int = 0
    total_cost_usd: float = 0.0
    permission_denials: list[dict[str, object]] = field(default_factory=list)


class ClaudeCodeError(Exception):
    """Raised when the bridge RPC fails or no bridge is available."""

    def __init__(self, message: str, returncode: int = -1) -> None:
        self.message = message
        self.returncode = returncode
        super().__init__(message)


class NoBridgeAvailableError(ClaudeCodeError):
    """Raised when no online bridge can satisfy the request."""

    def __init__(self, message: str = "Hiçbir aktif bridge bulunamadı") -> None:
        super().__init__(message, returncode=-1)


@dataclass
class _RunState:
    """Mutable per-run state aggregated as bridge events stream in.

    Mirrors the legacy ``_StreamState`` so the progress-event builder keeps
    the same shape, but no longer tracks subprocess-only fields.
    """

    session_id: str = ""
    model: str = ""
    response_text: str = ""
    duration_ms: int = 0
    tokens_input: int = 0
    tokens_output: int = 0
    tokens_cache_creation: int = 0
    tokens_cache_read: int = 0
    # T2.5-fix Bug 4 cursor: how many of state.tokens_input / .tokens_output
    # we already pushed to ``update_session_cost``. The result-event
    # persistence path computes ``state.tokens_X - state.tokens_X_persisted``
    # so assistant-event-supplied output_tokens (already added to
    # state.tokens_output before the result envelope arrives) are NOT
    # double-counted, AND so the result envelope's input_tokens (which is
    # the absolute usage rather than a delta) lands cumulatively without
    # being lost when the cursor was previously zero.
    tokens_input_persisted: int = 0
    tokens_output_persisted: int = 0
    cost_usd: float = 0.0
    permission_denials: list[dict[str, object]] = field(default_factory=list)
    delta_index: int = 0
    phase: str = "starting"
    current_tool_name: str | None = None
    tool_steps: list[ToolStepInfo] = field(default_factory=list)


class ClaudeCodeRunner:
    """RPC adapter — sends ``command.claude.run`` to a bridge.

    v2.0 contract:
        * ``__init__`` takes a :class:`BridgeRegistryService` (mandatory) and
          an optional :class:`SubagentRepository` for persistence.
        * ``run()`` keeps the legacy keyword-only signature plus four new
          optional callbacks (``on_session_init``, ``on_subagent_spawned``,
          ``on_subagent_progress``, ``on_subagent_completed``,
          ``on_rate_limit``). Existing callers that don't pass them are
          unaffected.
        * ``project_dir`` and ``append_system_prompt`` are still accepted
          for source compatibility but currently ignored — the bridge
          uses ``config.toml`` defaults. They will be wired through in
          a follow-up (project-aware dispatch lives in
          :class:`OrchestratorService`).
    """

    def __init__(
        self,
        bridge_registry: BridgeRegistryService | None = None,
        subagent_repo: SubagentRepository | None = None,
        session_repo: SessionRepository | None = None,
    ) -> None:
        # Resolve registry lazily so the legacy zero-arg constructor still
        # works for code paths that don't yet pass it explicitly.
        if bridge_registry is None:
            from app.services.bridge_registry_service import bridge_registry as _default

            bridge_registry = _default
        self._bridges = bridge_registry
        self._subagents = subagent_repo
        # T2.5: optional. When provided, the runner persists the per-result
        # cost+tokens onto the WebSocket session row identified by
        # ``db_session_id`` (passed to ``run()``). Left None for unit tests
        # and code paths that haven't migrated yet.
        self._sessions = session_repo

    async def run(
        self,
        *,
        prompt: str,
        session_id: str | None = None,
        project_dir: str | None = None,
        bridge_id: str | None = None,
        user_id: str | None = None,
        db_session_id: uuid.UUID | None = None,
        on_text_delta: TextDeltaCallback | None = None,
        on_tool_progress: ToolProgressCallback | None = None,
        on_question: QuestionCallback | None = None,
        on_stream_end: StreamEndCallback | None = None,
        on_session_init: SessionInitCallback | None = None,
        on_subagent_spawned: SubagentSpawnedCallback | None = None,
        on_subagent_progress: SubagentProgressCallback | None = None,
        on_subagent_completed: SubagentCompletedCallback | None = None,
        on_rate_limit: RateLimitCallback | None = None,
        on_permission_request: PermissionRequestCallback | None = None,
        append_system_prompt: str | None = None,  # noqa: ARG002 (forwarded later)
    ) -> ClaudeCodeResult:
        """Send a ``command.claude.run`` RPC to a bridge and stream events.

        Args:
            prompt: Orchestrator instruction passed to claude as the
                positional argument. Required.
            session_id: Existing claude session to resume. ``None`` starts
                a new session.
            project_dir: Optional project directory hint. Currently
                informational only — the bridge selects ``cwd`` from its
                ``config.toml``; a follow-up will plumb this through the
                ``command.claude.run`` payload.
            bridge_id: Specific bridge ``host_id`` to target. ``None``
                selects the least-busy online bridge with the
                ``claude_code`` capability.
            on_text_delta: Token-by-token text streaming callback.
            on_tool_progress: Progress event callback (synthesised from
                ``event.session.task_started`` / ``task_progress``).
            on_question: User-question callback (currently no bridge event
                surfaces this — wiring lands when ``AskUserQuestion`` is
                bridged in a later phase).
            on_stream_end: Stream completion callback receiving the final
                response text.
            on_session_init: Optional callback for ``event.session.init``.
            on_subagent_spawned: Optional callback for
                ``event.session.task_started``.
            on_subagent_progress: Optional callback for
                ``event.session.task_progress``.
            on_subagent_completed: Optional callback for
                ``event.session.task_notification``.
            on_rate_limit: Optional callback for
                ``event.session.rate_limit``.
            on_permission_request: Optional callback for
                ``event.session.permission_request`` (V1.4). Receives
                the freshly-created :class:`ApprovalRequestRecord`,
                ``bridge_host_id``, ``rpc_id`` (originating
                ``command.claude.run`` correlation_id), and
                ``timeout_seconds`` so the awaiter can dispatch the
                eventual ``command.claude.permission.{allow,deny}``
                envelope back. MUST be fire-and-forget — the runner's
                stream loop waits for nothing.
            append_system_prompt: Reserved (currently ignored; will be
                forwarded to the bridge once the RPC payload schema gains
                an ``append_system_prompt`` field — out of scope for T1.1).

        Returns:
            :class:`ClaudeCodeResult` with the terminal session state.

        Raises:
            NoBridgeAvailableError: No online bridge was available.
            ClaudeCodeError: Send failure or unexpected event-loop error.
        """
        # OpenTelemetry span — records the high-level run lifecycle. Attrs
        # use ``claude.*`` keys so dashboards can group cleanly. Prompt
        # *length* is recorded but never the prompt text itself (PII).
        with tracer.start_as_current_span(
            "claude.run",
            attributes={
                "claude.session_id": session_id or "",
                "claude.bridge_id": bridge_id or "",
                "claude.user_id": user_id or "",
                "claude.prompt_chars": len(prompt),
                "claude.permission_mode": "acceptEdits",
            },
        ) as run_span:
            try:
                return await self._run_inner(
                    prompt=prompt,
                    session_id=session_id,
                    project_dir=project_dir,
                    bridge_id=bridge_id,
                    user_id=user_id,
                    db_session_id=db_session_id,
                    on_text_delta=on_text_delta,
                    on_tool_progress=on_tool_progress,
                    on_question=on_question,
                    on_stream_end=on_stream_end,
                    on_session_init=on_session_init,
                    on_subagent_spawned=on_subagent_spawned,
                    on_subagent_progress=on_subagent_progress,
                    on_subagent_completed=on_subagent_completed,
                    on_rate_limit=on_rate_limit,
                    on_permission_request=on_permission_request,
                    span=run_span,
                )
            except ClaudeCodeError as exc:
                run_span.record_exception(exc)
                run_span.set_status(trace.Status(trace.StatusCode.ERROR, exc.message))
                raise

    async def _run_inner(
        self,
        *,
        prompt: str,
        session_id: str | None,
        project_dir: str | None,
        bridge_id: str | None,
        user_id: str | None,
        db_session_id: uuid.UUID | None,
        on_text_delta: TextDeltaCallback | None,
        on_tool_progress: ToolProgressCallback | None,
        on_question: QuestionCallback | None,
        on_stream_end: StreamEndCallback | None,
        on_session_init: SessionInitCallback | None,
        on_subagent_spawned: SubagentSpawnedCallback | None,
        on_subagent_progress: SubagentProgressCallback | None,
        on_subagent_completed: SubagentCompletedCallback | None,
        on_rate_limit: RateLimitCallback | None,
        on_permission_request: PermissionRequestCallback | None,
        span: trace.Span,
    ) -> ClaudeCodeResult:
        """Inner body of :meth:`run`, kept separate so the span context manager
        in the caller can wrap it without growing a deeply-nested ``with``.
        """
        # 1. Pick target bridge.
        target_host_id = self._select_bridge(bridge_id)
        if target_host_id is None:
            raise NoBridgeAvailableError()
        span.set_attribute("claude.bridge_host_id", target_host_id)

        connection_id = self._bridges.get_connection_id(target_host_id)
        if connection_id is None:
            raise NoBridgeAvailableError(
                f"Bridge '{target_host_id}' offline veya bağlantı yok",
            )

        # 2. Pre-register the event subscriber BEFORE sending the RPC so any
        #    early bridge envelopes (e.g. event.session.init that some bridges
        #    emit synchronously upon receiving command.claude.run) cannot race
        #    past the consumer. Folds in T1.1 reviewer H1 — see
        #    BridgeRegistryService.register_subscriber for details.
        rpc_id = uuid.uuid4().hex
        queue = self._bridges.register_subscriber(bridge_id=target_host_id, rpc_id=rpc_id)

        envelope: dict[str, object] = {
            "type": "command.claude.run",
            "id": rpc_id,
            "ts": datetime.now(tz=UTC).isoformat(),
            "correlation_id": rpc_id,
            "target": target_host_id,
            "payload": {
                "prompt": prompt,
                "session_id": session_id,
                "permission_mode": "acceptEdits",
                "agent_teams": True,
                "project_dir": project_dir,
                # H3: include user_id for log correlation. Bridge expects
                # a non-omitempty string; default to "" when caller didn't
                # pass it (matches the legacy zero-value behaviour).
                "user_id": user_id or "",
            },
        }

        sent = await self._bridges.send_to_bridge(target_host_id, envelope)
        if not sent:
            self._bridges.unregister_subscriber(bridge_id=target_host_id, rpc_id=rpc_id)
            raise ClaudeCodeError(
                f"Bridge '{target_host_id}' RPC gönderimi başarısız",
                returncode=-1,
            )

        # T2.2: start wall-clock for the duration histogram. The
        # ``claude_subprocess_count`` gauge is *set* from bridge
        # heartbeats in ``bridge_registry_service.process_heartbeat`` —
        # we don't dual-write it here to avoid racing two writers
        # against the same labelset.
        run_started_monotonic = time.monotonic()

        await logger.ainfo(
            "claude_rpc_sent",
            bridge_host_id=target_host_id,
            rpc_id=rpc_id,
            resume_session=session_id,
            user_id=user_id,
        )

        # 3. Consume typed events via the pre-registered subscriber queue.
        state = _RunState()
        callbacks = _Callbacks(
            on_text_delta=on_text_delta,
            on_tool_progress=on_tool_progress,
            on_question=on_question,
            on_stream_end=on_stream_end,
            on_session_init=on_session_init,
            on_subagent_spawned=on_subagent_spawned,
            on_subagent_progress=on_subagent_progress,
            on_subagent_completed=on_subagent_completed,
            on_rate_limit=on_rate_limit,
            on_permission_request=on_permission_request,
        )

        try:
            try:
                async for event in self._bridges.stream_events(
                    queue=queue,
                    rpc_id=rpc_id,
                    bridge_id=target_host_id,
                ):
                    terminal = await self._dispatch_event(
                        event=event,
                        state=state,
                        callbacks=callbacks,
                        bridge_host_id=target_host_id,
                        db_session_id=db_session_id,
                        user_id=user_id,
                        rpc_id=rpc_id,
                    )
                    if terminal:
                        break
            except ClaudeCodeError:
                raise
            except Exception as exc:  # pragma: no cover - defensive
                await logger.aexception("claude_rpc_unexpected_error", rpc_id=rpc_id)
                raise ClaudeCodeError(f"Bridge RPC error: {exc}") from exc
        finally:
            # T2.2: observe wall-clock duration + accumulate cost
            # regardless of how the run ended. Cost lives here so we
            # accumulate even if the caller short-circuits the
            # response_text consumer. Subprocess gauge is heartbeat-driven
            # in :class:`BridgeRegistryService` (see process_heartbeat).
            _metrics.claude_subprocess_duration_seconds.labels(
                bridge_id=target_host_id,
            ).observe(time.monotonic() - run_started_monotonic)
            if state.cost_usd > 0:
                _metrics.claude_total_cost_usd_total.labels(
                    bridge_id=target_host_id,
                    session_id=state.session_id or "unknown",
                ).inc(state.cost_usd)

        # 4. Final stream_end callback for legacy parity.
        if on_stream_end is not None:
            await on_stream_end(state.response_text)

        return ClaudeCodeResult(
            session_id=state.session_id,
            response_text=state.response_text,
            model_used=state.model,
            duration_ms=state.duration_ms,
            is_error=False,
            tokens_input=state.tokens_input,
            tokens_output=state.tokens_output,
            tokens_cache_creation=state.tokens_cache_creation,
            tokens_cache_read=state.tokens_cache_read,
            total_cost_usd=state.cost_usd,
            permission_denials=list(state.permission_denials),
        )

    async def cancel(self) -> None:
        """No-op for v2.0 — abort routing belongs to the bridge.

        Kept for API compatibility with v1 callers; aborting an in-flight
        run requires a separate ``command.claude.abort`` RPC carrying the
        session id (out of scope for T1.1; tracked in T1.x).
        """
        await logger.adebug("claude_runner_cancel_noop_v2")

    # ------------------------------------------------------------------
    # Internals.
    # ------------------------------------------------------------------

    def _select_bridge(self, bridge_id: str | None) -> str | None:
        """Pick a target bridge ``host_id``.

        Explicit ``bridge_id`` wins iff it's currently online; otherwise
        falls through to the least-busy online bridge with the
        ``claude_code`` capability.
        """
        if bridge_id is not None and self._bridges.get_connection_id(bridge_id) is not None:
            return bridge_id
        # Either no explicit pick or it's offline — fall back to capability-based selection.
        return self._bridges.find_online_agent_with_capability("claude_code")

    async def _dispatch_event(
        self,
        *,
        event: dict[str, object],
        state: _RunState,
        callbacks: _Callbacks,
        bridge_host_id: str,
        db_session_id: uuid.UUID | None = None,
        user_id: str | None = None,
        rpc_id: str = "",
    ) -> bool:
        """Route one bridge event to the right callback + state slot.

        Returns ``True`` when the event is terminal (``event.session.result``
        or an error/auth_expired event), telling the caller to break out of
        the stream loop.

        Each dispatch is wrapped in a ``claude.dispatch_event`` span so
        traces show the per-event work as children of the enclosing
        ``claude.run`` span. Subagent lifecycle transitions are recorded
        as span events (``subagent.spawned`` / ``subagent.completed``).
        """
        event_type_raw = event.get("type")
        event_type = str(event_type_raw) if event_type_raw is not None else ""
        with tracer.start_as_current_span(
            "claude.dispatch_event",
            attributes={
                "claude.event_type": event_type,
                "claude.bridge_host_id": bridge_host_id,
            },
        ) as span:
            try:
                return await self._dispatch_event_inner(
                    event=event,
                    state=state,
                    callbacks=callbacks,
                    bridge_host_id=bridge_host_id,
                    db_session_id=db_session_id,
                    user_id=user_id,
                    span=span,
                    rpc_id=rpc_id,
                )
            except ClaudeCodeError as exc:
                span.record_exception(exc)
                span.set_status(trace.Status(trace.StatusCode.ERROR, exc.message))
                raise

    async def _dispatch_event_inner(
        self,
        *,
        event: dict[str, object],
        state: _RunState,
        callbacks: _Callbacks,
        bridge_host_id: str,
        db_session_id: uuid.UUID | None,
        user_id: str | None,
        span: trace.Span,
        rpc_id: str = "",
    ) -> bool:
        """Body of :meth:`_dispatch_event`, wrapped by the OTel span."""
        event_type = event.get("type")
        payload = event.get("payload")
        if not isinstance(payload, dict):
            payload = {}

        # Server-side timestamp injection (T1.5 reviewer M3): bridges do
        # not include started_at/updated_at/completed_at. The forwarder
        # downstream may already inject these, but we make the runner
        # idempotent so a unit test exercising the runner directly always
        # sees timestamps present.
        now_iso = datetime.now(tz=UTC).isoformat()

        if event_type == "event.session.init":
            state.session_id = str(payload.get("session_id", ""))
            state.model = str(payload.get("model", ""))
            state.phase = "thinking"
            payload.setdefault("initialized_at", now_iso)
            if callbacks.on_session_init is not None:
                await callbacks.on_session_init(payload)
            if callbacks.on_tool_progress is not None:
                await callbacks.on_tool_progress(_build_progress_event(state))
            return False

        if event_type == "event.session.task_started":
            payload.setdefault("started_at", now_iso)
            span.add_event(
                "subagent.spawned",
                attributes={
                    "subagent.task_id": str(payload.get("task_id", "")),
                    "subagent.session_id": str(payload.get("session_id", "")),
                },
            )
            if callbacks.on_subagent_spawned is not None:
                await callbacks.on_subagent_spawned(payload)
            await self._persist_subagent_spawned(
                payload=payload,
                bridge_host_id=bridge_host_id,
                spawned_at=_parse_iso(payload.get("started_at"), default=now_iso),
            )
            return False

        if event_type == "event.session.task_progress":
            payload.setdefault("updated_at", now_iso)
            if callbacks.on_subagent_progress is not None:
                await callbacks.on_subagent_progress(payload)
            # Surface as classic progress for legacy iOS UI.
            if callbacks.on_tool_progress is not None:
                state.phase = str(payload.get("phase", "tool_calling"))
                state.current_tool_name = (
                    str(payload.get("current_tool")) if payload.get("current_tool") else None
                )
                await callbacks.on_tool_progress(_build_progress_event(state))
            return False

        if event_type == "event.session.task_notification":
            payload.setdefault("completed_at", now_iso)
            status_str = str(payload.get("status", "completed"))
            span.add_event(
                "subagent.completed",
                attributes={
                    "subagent.task_id": str(payload.get("task_id", "")),
                    "subagent.session_id": str(payload.get("session_id", "")),
                    "subagent.status": status_str,
                },
            )
            if status_str not in {"completed", "success", "ok"}:
                # Mark the dispatch span as error so dashboards can filter
                # subagent failures cheaply (without grep'ing event attrs).
                span.set_status(
                    trace.Status(
                        trace.StatusCode.ERROR,
                        f"subagent terminal status: {status_str}",
                    )
                )
            if callbacks.on_subagent_completed is not None:
                await callbacks.on_subagent_completed(payload)
            await self._persist_subagent_completed(
                payload=payload,
                bridge_host_id=bridge_host_id,
                completed_at=_parse_iso(payload.get("completed_at"), default=now_iso),
            )
            return False

        if event_type == "event.session.rate_limit":
            rate_limit_type = str(payload.get("rate_limit_type") or "unknown")
            _metrics.claude_rate_limit_hits_total.labels(
                bridge_id=bridge_host_id,
                rate_limit_type=rate_limit_type,
            ).inc()
            if callbacks.on_rate_limit is not None:
                await callbacks.on_rate_limit(payload)
            return False

        if event_type == "event.session.stream":
            # Partial assistant message — surface as a text delta.
            delta = payload.get("delta")
            text = _extract_delta_text(delta)
            if text:
                if state.phase != "generating":
                    state.phase = "generating"
                    if callbacks.on_tool_progress is not None:
                        await callbacks.on_tool_progress(_build_progress_event(state))
                state.response_text += text
                if callbacks.on_text_delta is not None:
                    await callbacks.on_text_delta(text, state.delta_index)
                state.delta_index += 1
            return False

        if event_type == "event.session.assistant":
            # A complete assistant message — accumulate text + bump tokens.
            message = payload.get("message")
            text, out_tokens = _extract_assistant_text_and_tokens(message)
            if text and not state.response_text:
                state.response_text = text
                if callbacks.on_text_delta is not None:
                    await callbacks.on_text_delta(text, state.delta_index)
                state.delta_index += 1
            if out_tokens:
                state.tokens_output += out_tokens
            return False

        if event_type == "event.session.user":
            # Tool result echo — currently ignored; future hook for
            # surfacing tool outputs to the UI.
            return False

        if event_type == "event.session.permission_request":
            # V1.4 — bridge PreToolUse hook intercepted a tool call and
            # is asking for the user's verdict. We translate the bridge
            # envelope into an :class:`ApprovalRequestRecord`, hand the
            # routing trio (host, rpc, request) to the websocket-layer
            # callback, then return immediately so the runner's stream
            # loop keeps consuming further envelopes (subagents may
            # raise concurrent permission_requests). The callback owns
            # the iOS push + decision-await + bridge-reply round-trip
            # in a fire-and-forget asyncio.Task.
            await self._handle_permission_request(
                payload=payload,
                state=state,
                callbacks=callbacks,
                bridge_host_id=bridge_host_id,
                rpc_id=rpc_id,
            )
            return False

        if event_type == "event.session.result":
            state.duration_ms = int(payload.get("duration_ms", 0) or 0)
            result_text = payload.get("result")
            if isinstance(result_text, str) and result_text:
                if not state.response_text:
                    state.response_text = result_text
                    if callbacks.on_text_delta is not None:
                        await callbacks.on_text_delta(result_text, state.delta_index)
                        state.delta_index += 1
                else:
                    state.response_text = result_text
            cost = payload.get("total_cost_usd")
            if isinstance(cost, (int, float)):
                state.cost_usd = float(cost)
            denials = payload.get("permission_denials")
            if isinstance(denials, list):
                state.permission_denials = [d for d in denials if isinstance(d, dict)]
            # Aggregate token usage from per-model breakdown. T2.5 also
            # tracks the two prompt-cache buckets so the cost-summary
            # endpoint can report them separately.
            usage = payload.get("model_usage")
            cache_creation_delta = 0
            cache_read_delta = 0
            input_delta = 0
            output_from_usage = 0
            if isinstance(usage, dict):
                for entry in usage.values():
                    if isinstance(entry, dict):
                        input_delta += int(entry.get("input_tokens", 0) or 0)
                        cache_creation_delta += int(
                            entry.get("cache_creation_input_tokens", 0) or 0
                        )
                        cache_read_delta += int(entry.get("cache_read_input_tokens", 0) or 0)
                        output_from_usage += int(entry.get("output_tokens", 0) or 0)

            state.tokens_input += input_delta
            state.tokens_cache_creation += cache_creation_delta
            state.tokens_cache_read += cache_read_delta
            # Don't double-count output_tokens that the assistant events
            # already reported; prefer the final usage breakdown when
            # assistant events didn't surface counts.
            output_delta = output_from_usage if state.tokens_output == 0 else 0
            state.tokens_output += output_delta

            state.phase = "completed"
            if callbacks.on_tool_progress is not None:
                await callbacks.on_tool_progress(_build_progress_event(state))

            # T2.5 — persist per-result cost+tokens. Best-effort: if no
            # ``session_repo`` was injected (legacy code path), no
            # ``db_session_id`` was supplied, or no ``user_id`` was
            # threaded through (the UPSERT requires it because the row
            # may not yet exist and ``sessions.user_id`` is NOT NULL FK),
            # we silently skip — this is purely additive to the existing
            # claude_total_cost_usd_total Prometheus counter (T2.2).
            #
            # T2.5-fix Bug 4 (cursor): persist deltas measured against the
            # already-persisted cumulative count, not the per-event
            # increments. This handles the case where assistant events
            # populated state.tokens_output BEFORE the result envelope
            # arrived (otherwise the result-event "output_delta = 0 if
            # state.tokens_output != 0" guard would push 0 to the DB,
            # silently losing the assistant-reported counts).
            if self._sessions is not None and db_session_id is not None and user_id:
                try:
                    from decimal import Decimal

                    output_to_persist = state.tokens_output - state.tokens_output_persisted
                    state.tokens_output_persisted = state.tokens_output
                    input_to_persist = state.tokens_input - state.tokens_input_persisted
                    state.tokens_input_persisted = state.tokens_input

                    await self._sessions.update_session_cost(
                        db_session_id,
                        user_id=uuid.UUID(user_id),
                        total_cost_usd=Decimal(str(state.cost_usd)),
                        total_input_tokens=input_to_persist,
                        total_output_tokens=output_to_persist,
                        total_cache_creation_tokens=cache_creation_delta,
                        total_cache_read_tokens=cache_read_delta,
                    )
                except Exception:
                    await logger.aexception(
                        "session_cost_persist_failed",
                        session_id=str(db_session_id),
                    )
            return True

        if event_type in {"event.bridge.auth_expired"}:
            raise ClaudeCodeError(
                "Bridge authentication expired",
                returncode=-1,
            )

        # Unknown event types are logged and ignored — keeps the runner
        # forward-compatible with new bridge envelopes.
        await logger.adebug("claude_rpc_unknown_event", type=event_type)
        return False

    # ------------------------------------------------------------------
    # Permission-request handling (V1.4).
    # ------------------------------------------------------------------

    async def _handle_permission_request(
        self,
        *,
        payload: dict[str, object],
        state: _RunState,
        callbacks: _Callbacks,
        bridge_host_id: str,
        rpc_id: str,
    ) -> None:
        """Translate a bridge ``permission_request`` envelope into an
        :class:`ApprovalRequestRecord` and dispatch the routing trio.

        Risk → :class:`ApprovalCategory` mapping mirrors the design
        doc V1.4 §2.1.3 risk table:

        * ``high`` → ``DESTRUCTIVE`` (Bash off-whitelist, WebFetch,
          unknown tools — deny-default tier)
        * ``medium`` → ``WRITE_REMOTE`` (Edit/Write within cwd,
          Bash whitelist hit)
        * ``low`` → ``INFRASTRUCTURE`` (Read/Glob/Grep — should rarely
          hit the hook because acceptEdits already greenlights them,
          but kept for symmetry with the bridge enum)

        Anything outside the three known risk values defaults to the
        most-conservative ``DESTRUCTIVE`` so a malformed envelope
        produces a real approval prompt rather than a silent allow.

        Routing trio: ``rpc_id`` is the originating
        ``command.claude.run`` correlation_id (= the runner's own
        rpc_id, threaded through ``_dispatch_event`` →
        ``_dispatch_event_inner`` → here) so the eventual decision RPC
        carries the same correlation_id and the bridge's inbound
        dispatcher routes the reply to the correct broker invocation.
        """
        from app.schemas.approval import (
            ApprovalCategory,
            ApprovalRequestCreate,
        )
        from app.services.approval_service import get_approval_service

        request_id = str(payload.get("request_id", ""))
        tool_name = str(payload.get("tool_name", ""))
        risk = str(payload.get("risk", "high"))
        input_preview_raw = payload.get("input_preview")
        input_preview = str(input_preview_raw) if input_preview_raw is not None else ""
        timeout_ms_raw = payload.get("timeout_ms", 30_000)
        timeout_ms = (
            int(timeout_ms_raw) if isinstance(timeout_ms_raw, (int, float)) else 30_000
        )
        # V1.4-fix LOW: cap at 600s so a malicious or buggy bridge envelope
        # cannot persist arbitrarily large bridge_timeout_seconds. The
        # backend's per-category max is 300s; 600s gives 2x headroom.
        timeout_seconds = min(600, max(1, (timeout_ms + 999) // 1000))

        # V1.4-fix LOW: bridge protocol REQUIRES request_id (design §2.1.4).
        # Empty value is a protocol violation; record will fall back to its
        # backend-side approval UUID for the dispatched envelope, which the
        # bridge broker will not match → hook denies on its own timeout.
        # Log so SREs can see it.
        if not request_id:
            await logger.awarning(
                "bridge_envelope_missing_request_id",
                bridge_host_id=bridge_host_id,
                tool_name=tool_name,
            )

        risk_to_category: dict[str, ApprovalCategory] = {
            "high": ApprovalCategory.DESTRUCTIVE,
            "medium": ApprovalCategory.WRITE_REMOTE,
            "low": ApprovalCategory.INFRASTRUCTURE,
        }
        category = risk_to_category.get(risk, ApprovalCategory.DESTRUCTIVE)

        session_id_for_record = state.session_id or str(payload.get("session_id", ""))

        # The bridge envelope's input_preview is intentionally kept
        # short (240 bytes per design §2.1.3) — never log the raw
        # tool_input here even at debug, which may carry secrets
        # (Bash command, file paths). See design §4.5 privacy note.
        await logger.adebug(
            "permission_request_received",
            bridge_host_id=bridge_host_id,
            request_id=request_id,
            tool_name=tool_name,
            risk=risk,
        )

        approval_service = get_approval_service()
        request = ApprovalRequestCreate(
            session_id=session_id_for_record,
            connection_id="",  # filled by the awaiter when it knows the iOS conn
            tool_name=tool_name,
            action=tool_name,
            description=input_preview or f"{tool_name} tool çağrısı için onay gerekli",
            params=None,
            category=category,
            timeout_seconds=timeout_seconds,
            request_id=request_id or None,
            bridge_host_id=bridge_host_id,
            rpc_id=rpc_id or None,
            # V1.4-fix MEDIUM #1: pass bridge timeout explicitly so
            # build_question_message can render the correct iOS countdown.
            bridge_timeout_seconds=timeout_seconds,
        )
        record = await approval_service.create_approval(request)

        # Prometheus increment: emitted counter is the SLI for "how many
        # PreToolUse hooks fired". The decided + timeout counters land
        # in the awaiter (see websocket._await_and_dispatch_decision).
        _metrics.permission_request_emitted_total.labels(
            bridge_id=bridge_host_id,
            tool_name=tool_name or "unknown",
            risk=risk or "unknown",
        ).inc()

        if callbacks.on_permission_request is not None:
            # The callback already spawns its own asyncio.Task internally
            # (see websocket._on_permission_request); awaiting this
            # invocation here is non-blocking because the callback returns
            # as soon as the spawn completes, so the runner's stream loop
            # is free to consume further bridge events while the user
            # decides.
            await callbacks.on_permission_request(
                record,
                bridge_host_id,
                rpc_id,
                timeout_seconds,
            )

    # ------------------------------------------------------------------
    # Subagent persistence.
    # ------------------------------------------------------------------

    async def _persist_subagent_spawned(
        self,
        *,
        payload: dict[str, object],
        bridge_host_id: str,
        spawned_at: datetime,
    ) -> None:
        """Best-effort upsert into the ``subagents`` table on task_started."""
        if self._subagents is None:
            return
        bridge_uuid = await self._resolve_bridge_uuid(bridge_host_id)
        if bridge_uuid is None:
            await logger.adebug(
                "subagent_persist_skipped_unknown_bridge",
                bridge_host_id=bridge_host_id,
            )
            return

        session_id = str(payload.get("session_id", ""))
        task_id = str(payload.get("task_id", ""))
        if not session_id or not task_id:
            return

        prompt_preview = _stringify_optional(payload.get("prompt_preview"))
        try:
            await self._subagents.upsert_subagent(
                bridge_id=bridge_uuid,
                session_id=session_id,
                task_id=task_id,
                spawned_at=spawned_at,
                name=_stringify_optional(payload.get("name"))
                or _stringify_optional(payload.get("description")),
                description=_stringify_optional(payload.get("description")),
                prompt_preview=prompt_preview,
                subagent_type=_stringify_optional(payload.get("subagent_type")),
                isolation=_stringify_optional(payload.get("isolation")),
                status="spawned",
            )
        except Exception:
            await logger.aexception(
                "subagent_spawn_persist_failed",
                session_id=session_id,
                task_id=task_id,
            )

    async def _persist_subagent_completed(
        self,
        *,
        payload: dict[str, object],
        bridge_host_id: str,
        completed_at: datetime,
    ) -> None:
        """Best-effort UPDATE on ``subagents`` for terminal task_notification.

        Folds in T1.1 reviewer H2 (missed-spawn fallback): if the matching
        ``(session_id, task_id)`` row is missing — typically because the
        backend restarted between ``task_started`` and ``task_notification``
        and the spawn event was never persisted — we synthesise a row via
        :meth:`SubagentRepository.upsert_subagent` with
        ``spawned_at = completed_at - 1ms`` so the table stays consistent
        and the late arrival isn't silently dropped.
        """
        if self._subagents is None:
            return

        session_id = str(payload.get("session_id", ""))
        task_id = str(payload.get("task_id", ""))
        if not session_id or not task_id:
            return

        status = str(payload.get("status", "completed"))
        summary = _stringify_optional(payload.get("summary"))
        total_tokens = _optional_int(payload.get("total_tokens"))
        tool_uses = _optional_int(payload.get("tool_uses"))
        duration_ms = _optional_int(payload.get("duration_ms"))

        try:
            updated = await self._subagents.update_subagent_status(
                session_id=session_id,
                task_id=task_id,
                status=status,
                summary=summary,
                total_tokens=total_tokens,
                tool_uses=tool_uses,
                duration_ms=duration_ms,
                completed_at=completed_at,
            )
        except Exception:
            await logger.aexception(
                "subagent_complete_persist_failed",
                session_id=session_id,
                task_id=task_id,
            )
            return

        if updated:
            return

        # H2: row didn't exist — backend missed the task_started envelope.
        # Synthesise a spawn row so the completion stays auditable. Tag the
        # entry as ``late_arrival`` via the description prefix so operators
        # can grep for it (the schema has no metadata column today).
        await logger.awarning(
            "subagent_complete_missed_spawn",
            session_id=session_id,
            task_id=task_id,
        )
        bridge_uuid = await self._resolve_bridge_uuid(bridge_host_id)
        if bridge_uuid is None:
            await logger.adebug(
                "subagent_complete_late_skip_unknown_bridge",
                bridge_host_id=bridge_host_id,
                session_id=session_id,
                task_id=task_id,
            )
            return

        spawned_at = completed_at - timedelta(milliseconds=1)
        late_description = "[late_arrival] " + (
            _stringify_optional(payload.get("description")) or "subagent"
        )
        try:
            await self._subagents.upsert_subagent(
                bridge_id=bridge_uuid,
                session_id=session_id,
                task_id=task_id,
                spawned_at=spawned_at,
                name=_stringify_optional(payload.get("name"))
                or _stringify_optional(payload.get("description")),
                description=late_description,
                prompt_preview=_stringify_optional(payload.get("prompt_preview")),
                subagent_type=_stringify_optional(payload.get("subagent_type")),
                isolation=_stringify_optional(payload.get("isolation")),
                status=status,
                summary=summary,
                total_tokens=total_tokens,
                tool_uses=tool_uses,
                duration_ms=duration_ms,
                completed_at=completed_at,
            )
        except Exception:
            await logger.aexception(
                "subagent_complete_late_upsert_failed",
                session_id=session_id,
                task_id=task_id,
            )

    async def _resolve_bridge_uuid(self, host_id: str) -> uuid.UUID | None:
        """Translate a bridge ``host_id`` to its DB primary-key UUID.

        Used only when ``SubagentRepository`` is configured. Returns
        ``None`` when the bridge isn't yet persisted (e.g. tests don't
        spin up the DB).
        """
        try:
            from app.core.database import async_session_factory
            from app.repositories.bridge_repo import BridgeRepository

            async with async_session_factory() as db:
                repo = BridgeRepository(db)
                bridge = await repo.get_by_host_id(host_id)
                if bridge is None:
                    return None
                return bridge.id
        except Exception:  # pragma: no cover - defensive
            await logger.adebug("bridge_uuid_resolve_failed", host_id=host_id)
            return None


# ---------------------------------------------------------------------------
# Internal helpers.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Callbacks:
    """Pack of optional callbacks; passing this around keeps signatures sane."""

    on_text_delta: TextDeltaCallback | None
    on_tool_progress: ToolProgressCallback | None
    on_question: QuestionCallback | None
    on_stream_end: StreamEndCallback | None
    on_session_init: SessionInitCallback | None
    on_subagent_spawned: SubagentSpawnedCallback | None
    on_subagent_progress: SubagentProgressCallback | None
    on_subagent_completed: SubagentCompletedCallback | None
    on_rate_limit: RateLimitCallback | None
    on_permission_request: PermissionRequestCallback | None


def _build_progress_event(state: _RunState) -> ToolProgressEvent:
    """Build a snapshot ``ToolProgressEvent`` from the current run state."""
    pct = {
        "starting": 5,
        "thinking": 15,
        "tool_calling": 50,
        "generating": 85,
        "completed": 100,
    }.get(state.phase, 10)

    phase_labels = {
        "starting": "Başlatılıyor...",
        "thinking": "Düşünüyor...",
        "tool_calling": (
            _tool_display_name(state.current_tool_name)
            if state.current_tool_name
            else "İşlem yapılıyor..."
        ),
        "generating": "Cevap hazırlanıyor...",
        "completed": "Tamamlandı",
    }
    return ToolProgressEvent(
        phase=state.phase,
        phase_label=phase_labels.get(state.phase, state.phase),
        current_tool=state.current_tool_name,
        percentage=pct,
        steps=list(state.tool_steps),
    )


def _extract_delta_text(delta: object) -> str:
    """Extract text from an ``event.session.stream`` delta payload.

    The bridge passes the claude SSE delta verbatim. Two shapes are
    common: a top-level ``text_delta`` or a nested ``content_block_delta``.
    """
    if not isinstance(delta, dict):
        return ""
    delta_type = delta.get("type")
    if delta_type == "text_delta":
        text = delta.get("text", "")
        return text if isinstance(text, str) else ""
    inner = delta.get("delta")
    if isinstance(inner, dict):
        return _extract_delta_text(inner)
    # Some bridges wrap the partial in a content_block_delta envelope.
    block = delta.get("content_block_delta") or delta.get("content_block")
    if isinstance(block, dict):
        return _extract_delta_text(block)
    return ""


def _extract_assistant_text_and_tokens(message: object) -> tuple[str, int]:
    """Pull text content + output_tokens from an assistant message blob."""
    if not isinstance(message, (dict, str)):
        return "", 0
    if isinstance(message, str):
        # Some bridges send raw JSON strings.
        try:
            message = json.loads(message)
        except json.JSONDecodeError:
            return "", 0
    if not isinstance(message, dict):
        return "", 0

    text_parts: list[str] = []
    content = message.get("content")
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                t = block.get("text", "")
                if isinstance(t, str):
                    text_parts.append(t)

    out_tokens = 0
    usage = message.get("usage")
    if isinstance(usage, dict):
        out_tokens = int(usage.get("output_tokens", 0) or 0)

    return "".join(text_parts), out_tokens


def _stringify_optional(value: object) -> str | None:
    """Convert an arbitrary payload field to ``str`` while preserving ``None``."""
    if value is None:
        return None
    if isinstance(value, str):
        return value or None
    return str(value)


def _optional_int(value: object) -> int | None:
    """Coerce an arbitrary payload field to ``int`` or ``None``."""
    if value is None:
        return None
    if isinstance(value, bool):
        # bool is a subclass of int; reject explicit booleans so we don't
        # silently coerce a `True` flag into 1.
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _parse_iso(value: object, *, default: str) -> datetime:
    """Parse an ISO-8601 timestamp from a payload, falling back to ``default``."""
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(default.replace("Z", "+00:00"))
    except ValueError:  # pragma: no cover - default is always valid ISO
        return datetime.now(tz=UTC)


# ---------------------------------------------------------------------------
# AsyncIterator typing helper — lets static checkers infer the return type
# of ``BridgeRegistryService.stream_events`` without importing the service
# module here (which would create a cycle at runtime).
# ---------------------------------------------------------------------------

EventStream = AsyncIterator[dict[str, object]]
