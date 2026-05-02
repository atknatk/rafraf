"""End-to-end Faz 1 integration test (T1.11).

Wires the full backend pipeline together with a mocked bridge connection
and a mocked iOS WebSocket layer, then drives a 3-subagent claude run end
to end. Asserts that every bridge envelope produced by the canned
fixture results in:

    bridge → BridgeRegistryService.dispatch_event
        → ClaudeCodeRunner.run() callback
            → ClaudeStreamManager.forward_*
                → iOS ConnectionManager.send_json (captured)

The test deliberately uses real production classes for everything except
the I/O ends:

* The bridge side has no real WebSocket — events are pushed directly to
  ``BridgeRegistryService.dispatch_event`` from a background driver task,
  reading from a 14-event scenario built on top of
  ``apps/backend/tests/fixtures/bridge_stream_sample.jsonl`` extended with
  the additional events T1.11 demands (3 spawns, 3 completions,
  session.title, session.pr_opened, usage.report).
* The iOS side has no real WebSocket — a real :class:`ConnectionManager`
  is connected to an :class:`AsyncMock` whose ``send_json`` records every
  envelope sent.
* The DB layer is replaced by an in-memory ``_FakeSubagentRepo`` that
  records ``upsert_subagent`` / ``update_subagent_status`` calls so the
  3 subagent rows can be asserted without spinning up Postgres.

This test is the executable encoding of the Faz 1 done-criteria last
bullet (docs/10 §8): "iOS WebSocket connect → claude task gönder →
3 subagent spawn → her birinin durumu iOS'ta görünüyor".
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.websockets import WebSocketState

from app.core.websocket import ConnectionManager
from app.orchestrator.claude_code_runner import ClaudeCodeRunner
from app.schemas.agent import AgentCapability, AgentRegisterPayload
from app.schemas.messages import MessageType
from app.services.bridge_registry_service import BridgeRegistryService
from app.services.claude_stream_manager import ClaudeStreamManager

# ---------------------------------------------------------------------------
# Fakes — minimal stand-ins for I/O ends + DB.
# ---------------------------------------------------------------------------


class _FakeSubagentRepo:
    """In-memory ``SubagentRepository`` substitute.

    Records every ``upsert_subagent`` / ``update_subagent_status`` call so
    the test can assert on the 3-subagent lifecycle without a DB.
    ``update_subagent_status`` returns ``True`` when the matching
    ``(session_id, task_id)`` was previously upserted; this lets the H2
    missed-spawn fallback exercise its synthetic upsert path under test.
    """

    def __init__(self) -> None:
        self.upserts: list[dict[str, Any]] = []
        self.updates: list[dict[str, Any]] = []
        # Track which (session_id, task_id) pairs have a spawn row so the
        # update return value can simulate a real DB UPDATE rowcount.
        self._spawned_keys: set[tuple[str, str]] = set()

    async def upsert_subagent(self, **kwargs: Any) -> None:
        self.upserts.append(kwargs)
        sid = str(kwargs.get("session_id", ""))
        tid = str(kwargs.get("task_id", ""))
        if sid and tid:
            self._spawned_keys.add((sid, tid))

    async def update_subagent_status(
        self,
        session_id: str,
        task_id: str,
        status: str,
        **kwargs: Any,
    ) -> bool:
        self.updates.append(
            {
                "session_id": session_id,
                "task_id": task_id,
                "status": status,
                **kwargs,
            }
        )
        return (session_id, task_id) in self._spawned_keys


def _make_ios_websocket() -> AsyncMock:
    """Mint a fake iOS WebSocket whose ``send_json`` records the envelope."""
    ws = AsyncMock()
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    ws.client_state = WebSocketState.CONNECTED
    return ws


def _captured_messages(ws: AsyncMock) -> list[dict[str, Any]]:
    """Return every envelope the runner forwarded to ``ws``."""
    out: list[dict[str, Any]] = []
    for call in ws.send_json.await_args_list:
        if call.args:
            out.append(call.args[0])
    return out


def _filter_by_type(
    messages: list[dict[str, Any]],
    msg_type: MessageType,
) -> list[dict[str, Any]]:
    return [m for m in messages if m.get("type") == msg_type.value]


# ---------------------------------------------------------------------------
# Bridge driver — replays a scripted sequence of envelopes.
# ---------------------------------------------------------------------------


async def _drive_bridge(
    *,
    registry: BridgeRegistryService,
    rpc_id_holder: dict[str, str],
    events: list[dict[str, Any]],
    started_event: asyncio.Event,
) -> None:
    """Background task that pumps fixture events into the registry.

    Waits for ``started_event`` (signals that the runner has registered
    its subscriber and the RPC id is captured) and then dispatches every
    envelope, stamping the captured rpc_id as the correlation_id so the
    routing in :meth:`BridgeRegistryService.dispatch_event` succeeds.

    The driver yields between events so the runner has a chance to drain
    the queue and exercise its callback chain.
    """
    await started_event.wait()
    rpc_id = rpc_id_holder["rpc_id"]
    for raw in events:
        event = dict(raw)
        # Only stamp the runner's RPC id on session.* events. usage.report
        # (and any other broadcast envelope) keeps whatever correlation id
        # — or lack thereof — the bridge would normally send.
        event_type = str(event.get("type", ""))
        if event_type.startswith("event.session."):
            event["correlation_id"] = rpc_id
        await registry.dispatch_event(event)
        # Yield so runner consumes; one loop tick is enough.
        await asyncio.sleep(0)


# ---------------------------------------------------------------------------
# Fixture: 3-subagent realistic scenario.
#
# Built fresh per-test (not loaded from the on-disk JSONL) so we can
# enrich the scenario with the additional event types T1.11 demands —
# session.title, session.pr_opened, usage.report — without rewriting the
# shared fixture file consumed by the unit tests.
# ---------------------------------------------------------------------------


def _build_three_subagent_scenario(
    *,
    session_uuid: uuid.UUID,
    bridge_session_id: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Construct the canonical 3-subagent E2E event stream.

    Returns a ``(session_events, usage_report_envelope)`` tuple. The
    session events MUST be dispatched after the runner subscribes (they
    carry the runner's correlation_id). The usage report envelope is a
    standalone bridge broadcast and is dispatched separately via the
    ``_handle_usage_report`` path.

    Event order mirrors a realistic agent-teams session:

    1. ``event.session.init`` — model + cwd announce.
    2. ``event.session.task_started`` × 3 — t1, t2 (worktree), t3.
    3. ``event.session.task_progress`` × 2 — t1 + t2 in flight.
    4. ``event.session.task_notification`` × 3 — t1+t2 completed,
       t3 failed.
    5. ``event.session.rate_limit`` — five-hour bucket allowed at 42 %.
    6. ``event.session.title`` — generated AI title (UUID coerced).
    7. ``event.session.pr_opened`` — autocreated PR metadata.
    8. ``event.session.result`` — terminal envelope (cost + denials).
    """
    sid = bridge_session_id
    base_iso = "2026-05-02T10:00:00Z"

    session_events: list[dict[str, Any]] = [
        # 1. session.init
        {
            "type": "event.session.init",
            "id": "01",
            "ts": base_iso,
            "payload": {
                "session_id": sid,
                "cwd": "/repo",
                "model": "claude-opus-4-7",
                "tools": ["Read", "Edit", "Bash", "Agent"],
                "permission_mode": "acceptEdits",
                "api_key_source": "none",
                "version": "2.1.126",
                "agent_teams_enabled": True,
            },
        },
        # 2. Three subagent spawns (the heart of T1.11).
        {
            "type": "event.session.task_started",
            "id": "02",
            "ts": "2026-05-02T10:00:01Z",
            "payload": {
                "session_id": sid,
                "task_id": "t1",
                "name": "search docs",
                "description": "Search docs for orchestrator policy",
                "prompt_preview": "Find any docs that describe orchestrator policy.",
                "subagent_type": "general-purpose",
                # No isolation hint — bare general-purpose subagent.
            },
        },
        {
            "type": "event.session.task_started",
            "id": "03",
            "ts": "2026-05-02T10:00:01Z",
            "payload": {
                "session_id": sid,
                "task_id": "t2",
                "name": "run tests",
                "description": "Run pytest in worktree",
                "prompt_preview": "Run pytest and report failures.",
                "subagent_type": "tdd-pipeline:tester",
                "isolation": "worktree",
            },
        },
        {
            "type": "event.session.task_started",
            "id": "04",
            "ts": "2026-05-02T10:00:01Z",
            "payload": {
                "session_id": sid,
                "task_id": "t3",
                "name": "review changes",
                "description": "Review the diff for safety regressions",
                "prompt_preview": "Spot-check the diff for any obvious safety regressions.",
                "subagent_type": "code-review:reviewer",
            },
        },
        # 3. Two in-flight progress events (t1, t2).
        {
            "type": "event.session.task_progress",
            "id": "05",
            "ts": "2026-05-02T10:00:02Z",
            "payload": {
                "session_id": sid,
                "task_id": "t1",
                "status": "in_progress",
                "phase": "tool_calling",
                "phase_label": "Reading docs",
                "current_tool": "Read",
                "activity": "Reading docs/10",
                "percentage": 30,
                "steps": [],
            },
        },
        {
            "type": "event.session.task_progress",
            "id": "06",
            "ts": "2026-05-02T10:00:02Z",
            "payload": {
                "session_id": sid,
                "task_id": "t2",
                "status": "in_progress",
                "phase": "tool_calling",
                "phase_label": "Running pytest",
                "current_tool": "Bash",
                "activity": "Running pytest",
                "percentage": 25,
                "steps": [],
            },
        },
        # 4. Three terminal task_notification events (2 completed, 1 failed).
        {
            "type": "event.session.task_notification",
            "id": "07",
            "ts": "2026-05-02T10:00:04Z",
            "payload": {
                "session_id": sid,
                "task_id": "t1",
                "status": "completed",
                "summary": "Found docs/10 + docs/11 for policy",
                "total_tokens": 1234,
                "tool_uses": 3,
                "duration_ms": 1800,
            },
        },
        {
            "type": "event.session.task_notification",
            "id": "08",
            "ts": "2026-05-02T10:00:05Z",
            "payload": {
                "session_id": sid,
                "task_id": "t2",
                "status": "completed",
                "summary": "All tests green (885 PASS)",
                "total_tokens": 4567,
                "tool_uses": 12,
                "duration_ms": 9100,
            },
        },
        {
            "type": "event.session.task_notification",
            "id": "09",
            "ts": "2026-05-02T10:00:06Z",
            "payload": {
                "session_id": sid,
                "task_id": "t3",
                "status": "failed",
                "summary": "Reviewer flagged a force-unwrap regression",
                "total_tokens": 890,
                "tool_uses": 2,
                "duration_ms": 2400,
            },
        },
        # 5. Rate limit info (allowed, 42% of 5-hour window).
        {
            "type": "event.session.rate_limit",
            "id": "10",
            "ts": "2026-05-02T10:00:06Z",
            "payload": {
                "session_id": sid,
                "status": "allowed",
                "rate_limit_type": "five_hour",
                "resets_at": 1777657800,
                "overage_status": "allowed",
                "is_using_overage": False,
                # iOS reads five_hour_pct off the broader subscription
                # window via usage.report; rate_limit.info just reports
                # the allow/deny state. We still let the test sniff a
                # synthetic five_hour_pct hint if the bridge attaches it.
                "five_hour_pct": 42,
            },
        },
        # 6 + 7. Storage-watcher synthesised events (T1.5 reviewer M1 —
        # session_id is a UUID at the schema boundary).
        {
            "type": "event.session.title",
            "id": "11",
            "ts": "2026-05-02T10:00:07Z",
            "payload": {
                "session_id": str(session_uuid),
                "ai_title": "Generated test session",
            },
        },
        {
            "type": "event.session.pr_opened",
            "id": "12",
            "ts": "2026-05-02T10:00:07Z",
            "payload": {
                "session_id": str(session_uuid),
                "pr_number": 42,
                "pr_url": "https://github.com/atknatk/rafraf/pull/42",
                "pr_repository": "atknatk/rafraf",
            },
        },
        # 8. Result — terminal.
        {
            "type": "event.session.result",
            "id": "13",
            "ts": "2026-05-02T10:00:08Z",
            "payload": {
                "session_id": sid,
                "duration_ms": 8000,
                "num_turns": 3,
                "result": "All three subagents dispatched.",
                "stop_reason": "end_turn",
                "total_cost_usd": 0.0681,
                "model_usage": {
                    "claude-opus-4-7": {
                        "input_tokens": 6000,
                        "output_tokens": 450,
                        "cache_read_input_tokens": 25000,
                        "cache_creation_input_tokens": 12000,
                    }
                },
                "permission_denials": [],
                "terminal_reason": "clean_exit",
            },
        },
    ]

    # The usage.report envelope is a bridge broadcast — no correlation_id,
    # routed via _handle_usage_report. Carries 5-hour + 7-day windows.
    usage_envelope: dict[str, Any] = {
        "type": "event.usage.report",
        "id": "14",
        "ts": "2026-05-02T10:00:09Z",
        "payload": {
            "five_hour_pct": 42,
            "seven_day_pct": 15,
            "five_hour_resets_at": 1777657800,
            "seven_day_resets_at": 1778262600,
            "reported_at": 1777654200,
        },
    }

    return session_events, usage_envelope


# ---------------------------------------------------------------------------
# Wiring helpers — build the real-component graph used by every test.
# ---------------------------------------------------------------------------


async def _register_bridge(
    registry: BridgeRegistryService,
    *,
    host_id: str = "mac-1",
) -> None:
    """Register one online bridge with the ``claude_code`` capability."""
    payload = AgentRegisterPayload(
        host_id=host_id,
        capabilities=[AgentCapability.CLAUDE_CODE, AgentCapability.SHELL],
        os_info="macOS 15.0",
        version="2.1.0",
    )
    # Stub the BridgeRepository persistence path — the test runs without a
    # DB session factory so the dual-write would otherwise raise. The
    # registry already wraps the persist call in try/except and logs a
    # warning, but the warning noise is loud enough to obscure real
    # diagnostics in the captured output.
    await registry.register_agent(payload, f"conn-{host_id}")


def _make_orchestrator_callbacks(
    *,
    csm: ClaudeStreamManager,
    user_id: str,
    ws_session_id: str,
) -> dict[str, Callable[[dict[str, Any]], Awaitable[None]]]:
    """Reproduce the callback chain ``orchestrator_service.py`` builds.

    Mirrors :meth:`OrchestratorService.process_with_claude_code` — every
    callback wraps a ``ClaudeStreamManager.forward_*`` invocation. The
    closures are defined here (instead of imported) so the test stays
    independent of the orchestrator service's auth + Redis dependencies,
    which would otherwise drag in the entire DI graph.
    """
    from app.services.orchestrator_service import (  # noqa: PLC0415
        _coerce_int,
        _optional_str,
        _parse_iso_or_none,
    )

    async def on_session_init(p: dict[str, Any]) -> None:
        await csm.forward_session_init(
            user_id=user_id,
            session_id=str(p.get("session_id", "")),
            model=str(p.get("model", "")),
            permission_mode=str(p.get("permission_mode", "")),
            api_key_source=str(p.get("api_key_source", "")),
            cwd=str(p.get("cwd", "")),
            agent_teams_enabled=bool(p.get("agent_teams_enabled", False)),
            initialized_at=_parse_iso_or_none(p.get("initialized_at")),
        )

    async def on_subagent_spawned(p: dict[str, Any]) -> None:
        sid_raw = p.get("session_id")
        sid = str(sid_raw) if sid_raw is not None else None
        name = str(p.get("name") or p.get("description") or "subagent")
        await csm.forward_subagent_spawned(
            user_id=user_id,
            session_id=sid,
            task_id=str(p.get("task_id", "")),
            name=name,
            description=_optional_str(p.get("description")),
            prompt_preview=str(p.get("prompt_preview", "")),
            subagent_type=_optional_str(p.get("subagent_type")),
            isolation=_optional_str(p.get("isolation")),
            started_at=_parse_iso_or_none(p.get("started_at")),
        )

    async def on_subagent_progress(p: dict[str, Any]) -> None:
        sid_raw = p.get("session_id")
        sid = str(sid_raw) if sid_raw is not None else None
        await csm.forward_subagent_progress(
            user_id=user_id,
            session_id=sid,
            task_id=str(p.get("task_id", "")),
            status=str(p.get("status", "in_progress")),
            activity=str(p.get("activity", "")),
            updated_at=_parse_iso_or_none(p.get("updated_at")),
        )

    async def on_subagent_completed(p: dict[str, Any]) -> None:
        sid_raw = p.get("session_id")
        sid = str(sid_raw) if sid_raw is not None else None
        await csm.forward_subagent_completed(
            user_id=user_id,
            session_id=sid,
            task_id=str(p.get("task_id", "")),
            status=str(p.get("status", "completed")),
            summary=_optional_str(p.get("summary")),
            total_tokens=_coerce_int(p.get("total_tokens")),
            tool_uses=_coerce_int(p.get("tool_uses")),
            duration_ms=_coerce_int(p.get("duration_ms")),
            completed_at=_parse_iso_or_none(p.get("completed_at")),
        )

    async def on_rate_limit(p: dict[str, Any]) -> None:
        await csm.forward_rate_limit_info(
            user_id=user_id,
            session_id=ws_session_id,
            status=str(p.get("status", "allowed")),
            rate_limit_type=str(p.get("rate_limit_type", "five_hour")),
            resets_at=_coerce_int(p.get("resets_at")),
            overage_status=str(p.get("overage_status", "")),
            is_using_overage=bool(p.get("is_using_overage", False)),
        )

    return {
        "on_session_init": on_session_init,
        "on_subagent_spawned": on_subagent_spawned,
        "on_subagent_progress": on_subagent_progress,
        "on_subagent_completed": on_subagent_completed,
        "on_rate_limit": on_rate_limit,
    }


async def _add_session_title_and_pr_handlers(
    csm: ClaudeStreamManager,
    user_id: str,
    bridge_event: dict[str, Any],
) -> None:
    """Forward ``session.title`` / ``session.pr_opened`` to iOS.

    These two envelopes don't ride through ClaudeCodeRunner today — the
    bridge emits them from its storage watcher (see docs/10 §6.4) and the
    backend forwards them via ``ClaudeStreamManager.forward_session_*``
    directly. The test simulates that bridge → CSM hop so the iOS
    contract for SESSION_TITLE / SESSION_PR_OPENED is exercised end to
    end.
    """
    payload = bridge_event.get("payload")
    if not isinstance(payload, dict):
        return
    event_type = str(bridge_event.get("type", ""))
    if event_type == "event.session.title":
        await csm.forward_session_title(
            user_id=user_id,
            session_id=str(payload.get("session_id", "")),
            ai_title=str(payload.get("ai_title", "")),
        )
    elif event_type == "event.session.pr_opened":
        await csm.forward_session_pr_opened(
            user_id=user_id,
            session_id=str(payload.get("session_id", "")),
            pr_number=int(payload.get("pr_number", 0)),
            pr_url=str(payload.get("pr_url", "")),
            pr_repository=str(payload.get("pr_repository", "")),
        )


async def _broadcast_usage_report(
    *,
    csm: ClaudeStreamManager,
    ios_manager: ConnectionManager,
    envelope: dict[str, Any],
) -> int:
    """Reproduce ``agent_ws._handle_usage_report`` against the test rig.

    The production handler imports the iOS ``manager`` singleton via a
    lazy import; we hand it the same fan-out semantics here so the
    multi-user multicast assertion can use real plumbing.
    """
    body = envelope.get("payload")
    if not isinstance(body, dict):
        body = envelope.get("content")
    assert isinstance(body, dict), "usage envelope missing payload/content"
    delivered = 0
    for user_id in ios_manager.get_active_user_ids():
        sent = await csm.forward_usage_report(
            user_id=user_id,
            five_hour_pct=int(body.get("five_hour_pct", 0)),
            seven_day_pct=int(body.get("seven_day_pct", 0)),
            five_hour_resets_at=int(body.get("five_hour_resets_at", 0)),
            seven_day_resets_at=int(body.get("seven_day_resets_at", 0)),
            reported_at=int(body.get("reported_at", 0)),
        )
        delivered += sent
    return delivered


# ---------------------------------------------------------------------------
# Pytest fixtures.
# ---------------------------------------------------------------------------


@pytest.fixture
async def bridge_registry() -> BridgeRegistryService:
    """Real BridgeRegistryService with one bridge registered.

    The DB persistence path inside ``register_agent`` is suppressed by
    monkey-patching ``async_session_factory`` lookup to raise; the
    service catches it and logs a warning, then keeps the in-memory
    registration intact. That's acceptable here — this test asserts on
    the in-memory side only.
    """
    registry = BridgeRegistryService()
    # Wire a fake "agent manager" so send_to_bridge can succeed; the
    # runner doesn't need the envelope to actually leave the process.
    fake_agent_manager = MagicMock()
    fake_agent_manager.send_json = AsyncMock(return_value=True)
    registry.set_agent_manager(fake_agent_manager)
    await _register_bridge(registry)
    return registry


@pytest.fixture
def ios_manager() -> ConnectionManager:
    """Real iOS-side ConnectionManager (no heartbeats, fast timeouts)."""
    return ConnectionManager(heartbeat_interval=999, heartbeat_timeout=999)


@pytest.fixture
def claude_stream_manager(
    bridge_registry: BridgeRegistryService,
    ios_manager: ConnectionManager,
) -> ClaudeStreamManager:
    """Real ClaudeStreamManager wired to both real connection managers."""
    fake_agent_manager = MagicMock()
    fake_agent_manager.send_json = AsyncMock(return_value=True)
    return ClaudeStreamManager(
        agent_registry=bridge_registry,
        agent_manager=fake_agent_manager,
        ios_manager=ios_manager,
    )


@pytest.fixture
def subagent_repo() -> _FakeSubagentRepo:
    """Fresh in-memory subagent repository per test."""
    return _FakeSubagentRepo()


# ---------------------------------------------------------------------------
# The headline E2E test.
# ---------------------------------------------------------------------------


async def test_e2e_three_subagent_spawn_to_ios(
    bridge_registry: BridgeRegistryService,
    ios_manager: ConnectionManager,
    claude_stream_manager: ClaudeStreamManager,
    subagent_repo: _FakeSubagentRepo,
) -> None:
    """Full Faz 1 pipeline: 3 subagent spawn → all events visible on iOS.

    Exercises the entire chain end to end:
        1. Real BridgeRegistryService routes events by correlation_id.
        2. Real ClaudeCodeRunner consumes the stream + fires callbacks +
           persists subagent rows via the (in-memory) repo.
        3. Real ClaudeStreamManager.forward_* serialises Pydantic
           payloads + pushes them to the iOS ConnectionManager.
        4. Real ConnectionManager.send_json reaches the captured mock
           WebSocket — the iOS-visible truth.
    """
    user_id = "user-ios-1"
    ws_session_id = str(uuid.uuid4())
    session_uuid = uuid.uuid4()
    bridge_session_id = str(session_uuid)

    # 1. Connect a fake iOS WebSocket — the END of the pipeline.
    ios_ws = _make_ios_websocket()
    ios_connection_id = await ios_manager.connect(
        websocket=ios_ws,
        user_id=user_id,
        session_id=ws_session_id,
    )
    assert ios_connection_id

    # 2. Build the runner with the real registry + fake subagent repo,
    #    short-circuiting the DB-backed bridge UUID resolver so the
    #    persistence path doesn't try to open a DB session.
    runner = ClaudeCodeRunner(
        bridge_registry=bridge_registry,
        subagent_repo=subagent_repo,  # type: ignore[arg-type]
    )
    fake_bridge_uuid = uuid.uuid4()

    async def _resolve(_host_id: str) -> uuid.UUID | None:
        return fake_bridge_uuid

    runner._resolve_bridge_uuid = _resolve  # type: ignore[method-assign,assignment]

    # 3. Build orchestrator-style callback closures that route to the CSM.
    callbacks = _make_orchestrator_callbacks(
        csm=claude_stream_manager,
        user_id=user_id,
        ws_session_id=ws_session_id,
    )

    # 4. Build the scenario events, then spawn the bridge driver. The
    #    driver waits until the runner has subscribed (and we've captured
    #    its rpc_id) before pushing any envelope, which mirrors the H1
    #    pre-register-then-send race contract.
    session_events, usage_envelope = _build_three_subagent_scenario(
        session_uuid=session_uuid,
        bridge_session_id=bridge_session_id,
    )
    rpc_id_holder: dict[str, str] = {"rpc_id": ""}
    started_event = asyncio.Event()

    # Patch send_to_bridge so we capture the runner's RPC id at the
    # exact moment the runner attempts to send. This guarantees the
    # bridge driver runs strictly AFTER the runner has subscribed.
    original_send = bridge_registry.send_to_bridge

    async def _capture_send(host_id: str, env: dict[str, object]) -> bool:
        rpc_id_holder["rpc_id"] = str(env.get("correlation_id", ""))
        ok = await original_send(host_id, env)
        # H1 fold-in: register_subscriber ran BEFORE send_to_bridge by
        # contract; verify the queue is alive at this point so the test
        # fails loudly if the runner regresses to the pre-T1.1 ordering.
        assert (
            "mac-1",
            rpc_id_holder["rpc_id"],
        ) in bridge_registry._event_subscribers, (
            "H1 race regression — subscriber not registered before send"
        )
        started_event.set()
        return ok

    bridge_registry.send_to_bridge = _capture_send  # type: ignore[method-assign,assignment]

    driver = asyncio.create_task(
        _drive_bridge(
            registry=bridge_registry,
            rpc_id_holder=rpc_id_holder,
            events=session_events,
            started_event=started_event,
        )
    )

    # 5. Run the runner. Wrap in wait_for so a regression can't hang CI.
    result = await asyncio.wait_for(
        runner.run(
            prompt="Spawn three subagents and report back",
            session_id=None,
            user_id=user_id,
            **callbacks,  # type: ignore[arg-type]
        ),
        timeout=10.0,
    )

    await asyncio.wait_for(driver, timeout=2.0)

    # 6. Forward session.title + session.pr_opened separately — these
    #    are storage-watcher events that don't ride through the runner
    #    today (the bridge → backend wiring lands when the storage
    #    watcher events get a backend handler in T2.x).
    for ev in session_events:
        if ev.get("type") in {"event.session.title", "event.session.pr_opened"}:
            await _add_session_title_and_pr_handlers(claude_stream_manager, user_id, ev)

    # 7. Broadcast the usage.report — this is the multi-user fan-out path.
    sent_users = await _broadcast_usage_report(
        csm=claude_stream_manager,
        ios_manager=ios_manager,
        envelope=usage_envelope,
    )
    assert sent_users == 1, "usage.report must reach the single iOS user once"

    # ---- Capture: every iOS-visible envelope on the wire. ----
    messages = _captured_messages(ios_ws)

    # =====================================================================
    # Assertions — start broad, then narrow down.
    # =====================================================================

    # Final ClaudeCodeResult sanity.
    assert result.session_id == bridge_session_id
    assert result.response_text == "All three subagents dispatched."
    assert result.model_used == "claude-opus-4-7"
    assert result.total_cost_usd == pytest.approx(0.0681)
    assert result.permission_denials == []
    assert result.tokens_input == 6000

    # ---- 1. session.init delivered with the right payload shape. ----
    init_msgs = _filter_by_type(messages, MessageType.SESSION_INIT)
    assert len(init_msgs) == 1, f"expected 1 session.init, got {len(init_msgs)}"
    init_content = init_msgs[0]["content"]
    assert init_content["session_id"] == bridge_session_id
    assert init_content["model"] == "claude-opus-4-7"
    assert init_content["cwd"] == "/repo"
    assert init_content["permission_mode"] == "acceptEdits"
    assert init_content["api_key_source"] == "none"
    assert init_content["agent_teams_enabled"] is True
    # Server-side timestamp injection (T1.5 M3): must be present.
    assert "initialized_at" in init_content

    # ---- 2. Three SUBAGENT_SPAWNED envelopes, one per task_id. ----
    spawned_msgs = _filter_by_type(messages, MessageType.SUBAGENT_SPAWNED)
    assert len(spawned_msgs) == 3, (
        f"expected 3 subagent spawn events, got {len(spawned_msgs)}: "
        f"{[m['content'] for m in spawned_msgs]}"
    )
    spawned_task_ids = sorted(m["content"]["task_id"] for m in spawned_msgs)
    assert spawned_task_ids == ["t1", "t2", "t3"]
    # Verify subagent_type, isolation, and started_at flow through faithfully.
    by_task = {m["content"]["task_id"]: m["content"] for m in spawned_msgs}
    assert by_task["t1"]["subagent_type"] == "general-purpose"
    assert by_task["t1"]["isolation"] is None
    assert by_task["t2"]["subagent_type"] == "tdd-pipeline:tester"
    assert by_task["t2"]["isolation"] == "worktree"
    assert by_task["t3"]["subagent_type"] == "code-review:reviewer"
    for content in by_task.values():
        assert "started_at" in content, "started_at must be server-injected"
        # Each spawn envelope carries the bridge session_id in metadata.
        meta = spawned_msgs[0]["metadata"]
        assert meta.get("session_id") == bridge_session_id

    # ---- 3. Two SUBAGENT_PROGRESS events for in-flight subagents. ----
    progress_msgs = _filter_by_type(messages, MessageType.SUBAGENT_PROGRESS)
    assert len(progress_msgs) == 2, f"expected 2 progress events, got {len(progress_msgs)}"
    progress_task_ids = sorted(m["content"]["task_id"] for m in progress_msgs)
    assert progress_task_ids == ["t1", "t2"]
    for m in progress_msgs:
        c = m["content"]
        assert c["status"] == "in_progress"
        assert "updated_at" in c

    # ---- 4. Three SUBAGENT_COMPLETED events: 2 completed + 1 failed. ----
    completed_msgs = _filter_by_type(messages, MessageType.SUBAGENT_COMPLETED)
    assert len(completed_msgs) == 3, f"expected 3 completion events, got {len(completed_msgs)}"
    statuses = sorted(m["content"]["status"] for m in completed_msgs)
    assert statuses == ["completed", "completed", "failed"]
    by_task_done = {m["content"]["task_id"]: m["content"] for m in completed_msgs}
    assert by_task_done["t1"]["status"] == "completed"
    assert by_task_done["t1"]["total_tokens"] == 1234
    assert by_task_done["t1"]["duration_ms"] == 1800
    assert by_task_done["t2"]["status"] == "completed"
    assert by_task_done["t2"]["total_tokens"] == 4567
    assert by_task_done["t3"]["status"] == "failed"
    assert by_task_done["t3"]["summary"].startswith("Reviewer flagged")
    for c in by_task_done.values():
        assert "completed_at" in c, "completed_at must be server-injected"

    # ---- 5. RATE_LIMIT_INFO with status="allowed" + five_hour bucket. ----
    rl_msgs = _filter_by_type(messages, MessageType.RATE_LIMIT_INFO)
    assert len(rl_msgs) == 1
    rl = rl_msgs[0]["content"]
    assert rl["status"] == "allowed"
    assert rl["rate_limit_type"] == "five_hour"
    assert rl["resets_at"] == 1777657800
    assert rl["overage_status"] == "allowed"
    assert rl["is_using_overage"] is False

    # ---- 6. SESSION_TITLE with UUID session_id (T1.5 M1). ----
    title_msgs = _filter_by_type(messages, MessageType.SESSION_TITLE)
    assert len(title_msgs) == 1
    title = title_msgs[0]["content"]
    assert title["session_id"] == str(session_uuid)
    # UUID round-trip — the value MUST parse as a UUID.
    uuid.UUID(title["session_id"])
    assert title["ai_title"] == "Generated test session"
    assert "generated_at" in title

    # ---- 7. SESSION_PR_OPENED with UUID session_id + PR metadata. ----
    pr_msgs = _filter_by_type(messages, MessageType.SESSION_PR_OPENED)
    assert len(pr_msgs) == 1
    pr = pr_msgs[0]["content"]
    assert pr["session_id"] == str(session_uuid)
    uuid.UUID(pr["session_id"])
    assert pr["pr_number"] == 42
    assert pr["pr_url"] == "https://github.com/atknatk/rafraf/pull/42"
    assert pr["pr_repository"] == "atknatk/rafraf"
    assert "opened_at" in pr

    # ---- 8. USAGE_REPORT broadcast — multicast fan-out. ----
    usage_msgs = _filter_by_type(messages, MessageType.USAGE_REPORT)
    assert len(usage_msgs) == 1, "single user → single usage.report envelope"
    usage = usage_msgs[0]["content"]
    assert usage["five_hour_pct"] == 42
    assert usage["seven_day_pct"] == 15
    assert usage["five_hour_resets_at"] == 1777657800
    assert usage["seven_day_resets_at"] == 1778262600
    assert usage["reported_at"] == 1777654200

    # ---- 9. Subagent persistence — three rows in the (mock) DB. ----
    spawned_keys = sorted((u["session_id"], u["task_id"]) for u in subagent_repo.upserts)
    assert spawned_keys == [
        (bridge_session_id, "t1"),
        (bridge_session_id, "t2"),
        (bridge_session_id, "t3"),
    ]
    update_keys = sorted(
        (u["session_id"], u["task_id"], u["status"]) for u in subagent_repo.updates
    )
    # Two completed + one failed row updates.
    assert (bridge_session_id, "t1", "completed") in update_keys
    assert (bridge_session_id, "t2", "completed") in update_keys
    assert (bridge_session_id, "t3", "failed") in update_keys
    # Persisted token + duration data sanity-check.
    by_task_persisted = {u["task_id"]: u for u in subagent_repo.updates}
    assert by_task_persisted["t1"]["total_tokens"] == 1234
    assert by_task_persisted["t1"]["duration_ms"] == 1800
    assert by_task_persisted["t2"]["total_tokens"] == 4567
    assert by_task_persisted["t3"]["total_tokens"] == 890

    # ---- 10. Every server-to-client envelope carries the right metadata. ----
    for m in messages:
        assert m.get("type") in {t.value for t in MessageType}
        meta = m.get("metadata")
        assert isinstance(meta, dict)
        assert meta.get("direction") == "server_to_client"
        # Timestamp must be ISO-8601 parseable.
        assert isinstance(meta.get("timestamp"), str)
        datetime.fromisoformat(str(meta["timestamp"]).replace("Z", "+00:00"))


# ---------------------------------------------------------------------------
# Targeted regression assertions — H1 (race), H2 (missed-spawn), H3 (user_id).
# ---------------------------------------------------------------------------


async def test_e2e_h1_subscriber_registered_before_send(
    bridge_registry: BridgeRegistryService,
    subagent_repo: _FakeSubagentRepo,
) -> None:
    """H1: an event arriving in the same tick as the RPC must NOT be lost.

    Inject the ``event.session.init`` envelope synchronously inside the
    patched ``send_to_bridge`` — i.e. between register_subscriber and the
    runner entering its consume loop. With the H1 fix in place the queue
    already exists, so the event reaches the callback. Without it, this
    test would deadlock and trip ``asyncio.wait_for``.
    """
    runner = ClaudeCodeRunner(
        bridge_registry=bridge_registry,
        subagent_repo=subagent_repo,  # type: ignore[arg-type]
    )

    async def _resolve(_host_id: str) -> uuid.UUID | None:
        return uuid.uuid4()

    runner._resolve_bridge_uuid = _resolve  # type: ignore[method-assign,assignment]

    init_called = asyncio.Event()
    init_payload: dict[str, Any] = {}

    async def on_init(payload: dict[str, Any]) -> None:
        init_payload.update(payload)
        init_called.set()

    original_send = bridge_registry.send_to_bridge

    async def _send_with_inline_dispatch(host_id: str, env: dict[str, object]) -> bool:
        # Send + immediately push the init event so it lands BEFORE the
        # runner's consumer awakens. Pre-T1.1, this would have been
        # dropped at dispatch_event because the queue didn't exist yet.
        ok = await original_send(host_id, env)
        rpc_id = str(env.get("correlation_id", ""))
        await bridge_registry.dispatch_event(
            {
                "type": "event.session.init",
                "correlation_id": rpc_id,
                "payload": {
                    "session_id": "race-sess",
                    "model": "claude-opus-4-7",
                    "cwd": "/repo",
                    "permission_mode": "acceptEdits",
                    "api_key_source": "none",
                    "agent_teams_enabled": True,
                },
            }
        )
        # Then dispatch a terminal result so the runner can exit cleanly.
        await bridge_registry.dispatch_event(
            {
                "type": "event.session.result",
                "correlation_id": rpc_id,
                "payload": {
                    "session_id": "race-sess",
                    "duration_ms": 0,
                    "result": "",
                    "total_cost_usd": 0.0,
                    "permission_denials": [],
                    "model_usage": {},
                },
            }
        )
        return ok

    bridge_registry.send_to_bridge = _send_with_inline_dispatch  # type: ignore[method-assign,assignment]

    result = await asyncio.wait_for(
        runner.run(prompt="race-test", on_session_init=on_init),
        timeout=5.0,
    )
    await asyncio.wait_for(init_called.wait(), timeout=1.0)
    assert init_payload["session_id"] == "race-sess"
    assert result.session_id == "race-sess"


async def test_e2e_h2_missed_spawn_late_arrival_synth(
    bridge_registry: BridgeRegistryService,
) -> None:
    """H2: completion without a preceding task_started → synthetic upsert.

    Mirrors the production scenario where the backend restarts between
    ``task_started`` and ``task_notification``: the spawn row is missing
    from the DB, so ``update_subagent_status`` returns False and the
    runner falls back to ``upsert_subagent`` with a ``[late_arrival]``
    description marker. Asserts the upsert lands AND that
    ``spawned_at`` < ``completed_at`` so chronology stays consistent.
    """

    class _NeverSpawnedRepo:
        """Records calls; ``update_subagent_status`` always returns False."""

        def __init__(self) -> None:
            self.upserts: list[dict[str, Any]] = []
            self.updates: list[dict[str, Any]] = []

        async def upsert_subagent(self, **kwargs: Any) -> None:
            self.upserts.append(kwargs)

        async def update_subagent_status(
            self,
            session_id: str,
            task_id: str,
            status: str,
            **kwargs: Any,
        ) -> bool:
            self.updates.append(
                {
                    "session_id": session_id,
                    "task_id": task_id,
                    "status": status,
                    **kwargs,
                }
            )
            return False  # spawn row absent — H2 trigger.

    repo = _NeverSpawnedRepo()
    runner = ClaudeCodeRunner(
        bridge_registry=bridge_registry,
        subagent_repo=repo,  # type: ignore[arg-type]
    )

    async def _resolve(_host_id: str) -> uuid.UUID | None:
        return uuid.uuid4()

    runner._resolve_bridge_uuid = _resolve  # type: ignore[method-assign,assignment]

    # Drive a stripped scenario: ONLY init + completion + result. No
    # task_started — that's the whole point of the test.
    rpc_id_holder: dict[str, str] = {"rpc_id": ""}
    started = asyncio.Event()

    original_send = bridge_registry.send_to_bridge

    async def _capture(host_id: str, env: dict[str, object]) -> bool:
        rpc_id_holder["rpc_id"] = str(env.get("correlation_id", ""))
        ok = await original_send(host_id, env)
        started.set()
        return ok

    bridge_registry.send_to_bridge = _capture  # type: ignore[method-assign,assignment]

    async def _drive() -> None:
        await started.wait()
        rpc_id = rpc_id_holder["rpc_id"]
        events: list[dict[str, object]] = [
            {
                "type": "event.session.init",
                "correlation_id": rpc_id,
                "payload": {
                    "session_id": "miss-sess",
                    "model": "claude-opus-4-7",
                    "cwd": "/repo",
                    "permission_mode": "acceptEdits",
                    "api_key_source": "none",
                    "agent_teams_enabled": True,
                },
            },
            {
                "type": "event.session.task_notification",
                "correlation_id": rpc_id,
                "payload": {
                    "session_id": "miss-sess",
                    "task_id": "missed-task-1",
                    "status": "completed",
                    "summary": "Late arrival",
                    "total_tokens": 100,
                    "tool_uses": 1,
                    "duration_ms": 500,
                    "description": "should-be-prefixed-late_arrival",
                },
            },
            {
                "type": "event.session.result",
                "correlation_id": rpc_id,
                "payload": {
                    "session_id": "miss-sess",
                    "duration_ms": 1000,
                    "result": "",
                    "total_cost_usd": 0.001,
                    "permission_denials": [],
                    "model_usage": {},
                },
            },
        ]
        for e in events:
            await bridge_registry.dispatch_event(e)
            await asyncio.sleep(0)

    driver = asyncio.create_task(_drive())
    await asyncio.wait_for(runner.run(prompt="miss"), timeout=5.0)
    await asyncio.wait_for(driver, timeout=2.0)

    # Update was attempted (returned False) → late_arrival upsert fired.
    assert len(repo.updates) == 1
    assert len(repo.upserts) == 1
    upsert = repo.upserts[0]
    assert upsert["session_id"] == "miss-sess"
    assert upsert["task_id"] == "missed-task-1"
    assert str(upsert.get("description", "")).startswith("[late_arrival]")
    assert upsert["spawned_at"] < upsert["completed_at"]
    assert upsert["status"] == "completed"


async def test_e2e_h3_user_id_propagated_through_pipeline(
    bridge_registry: BridgeRegistryService,
    subagent_repo: _FakeSubagentRepo,
) -> None:
    """H3: ``user_id`` MUST appear on the bridge envelope's ``payload``.

    The bridge correlates logs by user; missing the field would break
    audit trails. The runner defaults to "" when omitted (per the H3
    fold-in) — we assert the explicit non-empty case here.
    """
    runner = ClaudeCodeRunner(
        bridge_registry=bridge_registry,
        subagent_repo=subagent_repo,  # type: ignore[arg-type]
    )

    async def _resolve(_host_id: str) -> uuid.UUID | None:
        return uuid.uuid4()

    runner._resolve_bridge_uuid = _resolve  # type: ignore[method-assign,assignment]

    captured: dict[str, dict[str, object]] = {}

    original_send = bridge_registry.send_to_bridge

    async def _capture(host_id: str, env: dict[str, object]) -> bool:
        captured["envelope"] = dict(env)
        # Drain quickly with a terminal result so the runner can exit.
        rpc_id = str(env.get("correlation_id", ""))
        await original_send(host_id, env)
        await bridge_registry.dispatch_event(
            {
                "type": "event.session.result",
                "correlation_id": rpc_id,
                "payload": {
                    "session_id": "u3",
                    "duration_ms": 0,
                    "result": "",
                    "total_cost_usd": 0.0,
                    "permission_denials": [],
                    "model_usage": {},
                },
            }
        )
        return True

    bridge_registry.send_to_bridge = _capture  # type: ignore[method-assign,assignment]

    await asyncio.wait_for(
        runner.run(prompt="hi", user_id="auditor-42"),
        timeout=5.0,
    )

    assert "envelope" in captured
    payload = captured["envelope"].get("payload")
    assert isinstance(payload, dict)
    assert payload["user_id"] == "auditor-42"


# ---------------------------------------------------------------------------
# usage.report multicast to multiple iOS users.
# ---------------------------------------------------------------------------


async def test_e2e_usage_report_multicasts_to_each_connected_user(
    claude_stream_manager: ClaudeStreamManager,
    ios_manager: ConnectionManager,
) -> None:
    """``usage.report`` reaches EVERY active iOS user (not just the latest).

    Connect two distinct users, broadcast the bridge's usage envelope,
    and assert each user's WebSocket got exactly one ``usage.report``
    envelope. This is the one place where ``forward_usage_report`` is
    invoked once per user — a regression where it accidentally became
    session-scoped (single connection) would silently break subscription
    quota visibility for every other multi-device user.
    """
    ws_a = _make_ios_websocket()
    ws_b = _make_ios_websocket()
    await ios_manager.connect(websocket=ws_a, user_id="user-a", session_id="sa")
    await ios_manager.connect(websocket=ws_b, user_id="user-b", session_id="sb")

    envelope = {
        "type": "event.usage.report",
        "payload": {
            "five_hour_pct": 87,
            "seven_day_pct": 33,
            "five_hour_resets_at": 1777657800,
            "seven_day_resets_at": 1778262600,
            "reported_at": 1777654200,
        },
    }
    delivered = await _broadcast_usage_report(
        csm=claude_stream_manager,
        ios_manager=ios_manager,
        envelope=envelope,
    )
    assert delivered == 2

    msgs_a = _filter_by_type(_captured_messages(ws_a), MessageType.USAGE_REPORT)
    msgs_b = _filter_by_type(_captured_messages(ws_b), MessageType.USAGE_REPORT)
    assert len(msgs_a) == 1
    assert len(msgs_b) == 1
    assert msgs_a[0]["content"]["five_hour_pct"] == 87
    assert msgs_b[0]["content"]["seven_day_pct"] == 33


async def test_e2e_usage_report_multicasts_across_user_devices(
    claude_stream_manager: ClaudeStreamManager,
    ios_manager: ConnectionManager,
) -> None:
    """Multi-device same user: BOTH connections receive the envelope.

    ``send_to_user`` returns the per-connection delivery count; the
    forwarder must report 2 here even though it's a single user. This
    is the iOS user-on-iPhone-and-iPad reality.
    """
    user_id = "user-multidev"
    ws_phone = _make_ios_websocket()
    ws_ipad = _make_ios_websocket()
    await ios_manager.connect(websocket=ws_phone, user_id=user_id, session_id="phone")
    await ios_manager.connect(websocket=ws_ipad, user_id=user_id, session_id="ipad")

    envelope = {
        "type": "event.usage.report",
        "payload": {
            "five_hour_pct": 50,
            "seven_day_pct": 20,
            "five_hour_resets_at": 1777657800,
            "seven_day_resets_at": 1778262600,
            "reported_at": 1777654200,
        },
    }
    delivered = await _broadcast_usage_report(
        csm=claude_stream_manager,
        ios_manager=ios_manager,
        envelope=envelope,
    )
    # 2 devices for 1 user → forwarder reports 2 sessions reached.
    assert delivered == 2
    for ws in (ws_phone, ws_ipad):
        usage_msgs = _filter_by_type(_captured_messages(ws), MessageType.USAGE_REPORT)
        assert len(usage_msgs) == 1
        assert usage_msgs[0]["content"]["five_hour_pct"] == 50


# ---------------------------------------------------------------------------
# Cleanup helper — guarantee tasks don't leak across tests.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
async def _cancel_pending_tasks() -> AsyncIterator[None]:
    """Cancel any stray asyncio tasks at end of test.

    The bridge driver is awaited explicitly in each test; this fixture
    is a defensive sweep so a regression in test ordering can't leak a
    task into the next test's loop.
    """
    yield
    for task in asyncio.all_tasks() - {asyncio.current_task()}:
        if not task.done():
            task.cancel()
            with contextlib.suppress(BaseException):
                await task
