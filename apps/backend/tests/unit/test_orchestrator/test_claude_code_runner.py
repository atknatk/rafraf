"""Unit tests for ClaudeCodeRunner v2.0 (T1.1).

Strategy:
    * The Bridge → backend WS layer is mocked via a synthetic
      :class:`_FakeRegistry` that captures the outbound RPC envelope
      and replays a canned stream of events back through
      :meth:`stream_events`.
    * Subagent persistence is verified through an in-memory
      :class:`_FakeSubagentRepo` that records the upsert/update calls.
    * The end-to-end fixture (``bridge_stream_sample.jsonl``) walks the
      runner through the eight Agent-Teams event types and asserts the
      resulting callback ordering, response text, token aggregation,
      cost, and Subagent persistence.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from app.orchestrator.claude_code_runner import (
    ClaudeCodeError,
    ClaudeCodeResult,
    ClaudeCodeRunner,
    NoBridgeAvailableError,
    ToolProgressEvent,
)

# ---------------------------------------------------------------------------
# Fakes — minimal implementations of BridgeRegistryService + SubagentRepository
# ---------------------------------------------------------------------------


class _FakeRegistry:
    """Mimics the slice of BridgeRegistryService the runner depends on."""

    def __init__(
        self,
        *,
        events: list[dict[str, Any]] | None = None,
        send_succeeds: bool = True,
        online_host: str | None = "mac-1",
    ) -> None:
        self._events = list(events or [])
        self._send_succeeds = send_succeeds
        self._online_host = online_host
        # Populated by `send_to_bridge` so tests can inspect the RPC envelope.
        self.last_envelope: dict[str, Any] | None = None
        self.last_target: str | None = None

    def get_connection_id(self, host_id: str) -> str | None:
        if host_id == self._online_host:
            return f"conn-{host_id}"
        return None

    def find_online_agent_with_capability(self, capability: str) -> str | None:
        # Capability check is intentionally permissive — runner just needs a host.
        del capability
        return self._online_host

    async def send_to_bridge(
        self,
        host_id: str,
        envelope: dict[str, Any],
    ) -> bool:
        self.last_envelope = envelope
        self.last_target = host_id
        return self._send_succeeds

    async def stream_events(
        self,
        *,
        bridge_id: str,
        rpc_id: str,
    ) -> AsyncIterator[dict[str, Any]]:
        # Stamp every event's correlation_id to match the runner's rpc_id so
        # the fixture file is reusable across runs.
        del bridge_id  # unused in the fake
        for raw in self._events:
            event = dict(raw)
            event["correlation_id"] = rpc_id
            yield event


class _FakeSubagentRepo:
    """Records upsert/update calls in memory; no DB roundtrip."""

    def __init__(self) -> None:
        self.upserts: list[dict[str, Any]] = []
        self.updates: list[dict[str, Any]] = []

    async def upsert_subagent(self, **kwargs: Any) -> None:
        self.upserts.append(kwargs)

    async def update_subagent_status(self, *args: Any, **kwargs: Any) -> bool:
        # Match the real signature: positional (session_id, task_id, status)
        # plus kw-only fields. Normalise to a dict for assertion ergonomics.
        record: dict[str, Any] = {}
        if len(args) >= 1:
            record["session_id"] = args[0]
        if len(args) >= 2:
            record["task_id"] = args[1]
        if len(args) >= 3:
            record["status"] = args[2]
        record.update(kwargs)
        self.updates.append(record)
        return True


# ---------------------------------------------------------------------------
# Fixture loader.
# ---------------------------------------------------------------------------


_FIXTURE_PATH = (
    Path(__file__).resolve().parents[2] / "fixtures" / "bridge_stream_sample.jsonl"
)


def _load_sample_events() -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    with _FIXTURE_PATH.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            events.append(json.loads(line))
    return events


# ---------------------------------------------------------------------------
# Tests.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_dispatches_all_callbacks_in_order() -> None:
    """End-to-end run() with the 8-event fixture should fire every callback."""
    registry = _FakeRegistry(events=_load_sample_events())
    runner = ClaudeCodeRunner(bridge_registry=registry)  # type: ignore[arg-type]

    init_payloads: list[dict[str, Any]] = []
    spawned_payloads: list[dict[str, Any]] = []
    progress_payloads: list[dict[str, Any]] = []
    completed_payloads: list[dict[str, Any]] = []
    rate_limit_payloads: list[dict[str, Any]] = []
    text_deltas: list[tuple[str, int]] = []
    tool_progress_events: list[ToolProgressEvent] = []
    stream_end_calls: list[str] = []

    async def on_text_delta(delta: str, index: int) -> None:
        text_deltas.append((delta, index))

    async def on_tool_progress(ev: ToolProgressEvent) -> None:
        tool_progress_events.append(ev)

    async def on_stream_end(text: str) -> None:
        stream_end_calls.append(text)

    async def on_session_init(payload: dict[str, Any]) -> None:
        init_payloads.append(payload)

    async def on_subagent_spawned(payload: dict[str, Any]) -> None:
        spawned_payloads.append(payload)

    async def on_subagent_progress(payload: dict[str, Any]) -> None:
        progress_payloads.append(payload)

    async def on_subagent_completed(payload: dict[str, Any]) -> None:
        completed_payloads.append(payload)

    async def on_rate_limit(payload: dict[str, Any]) -> None:
        rate_limit_payloads.append(payload)

    result = await runner.run(
        prompt="ping",
        session_id=None,
        on_text_delta=on_text_delta,
        on_tool_progress=on_tool_progress,
        on_stream_end=on_stream_end,
        on_session_init=on_session_init,
        on_subagent_spawned=on_subagent_spawned,
        on_subagent_progress=on_subagent_progress,
        on_subagent_completed=on_subagent_completed,
        on_rate_limit=on_rate_limit,
    )

    assert isinstance(result, ClaudeCodeResult)
    assert result.session_id == "sess-abc"
    assert result.response_text == "Hello world"
    assert result.model_used == "claude-opus-4-7"
    assert result.duration_ms == 5000
    assert result.total_cost_usd == pytest.approx(0.0234)
    assert result.permission_denials == []
    assert result.tokens_input == 2000
    # Each callback fired exactly once for its dedicated event.
    assert len(init_payloads) == 1
    assert init_payloads[0]["session_id"] == "sess-abc"
    assert "initialized_at" in init_payloads[0]
    assert len(spawned_payloads) == 1
    assert spawned_payloads[0]["task_id"] == "task-1"
    assert "started_at" in spawned_payloads[0]
    assert len(progress_payloads) == 1
    assert "updated_at" in progress_payloads[0]
    assert len(completed_payloads) == 1
    assert completed_payloads[0]["status"] == "completed"
    assert "completed_at" in completed_payloads[0]
    assert len(rate_limit_payloads) == 1
    # Two stream deltas + one final stream_end.
    assert text_deltas == [("Hello ", 0), ("world", 1)]
    assert stream_end_calls == ["Hello world"]
    # Tool progress should fire at least for init, task_progress, and result.
    phases = [ev.phase for ev in tool_progress_events]
    assert "thinking" in phases
    assert "completed" in phases


@pytest.mark.asyncio
async def test_run_sends_command_claude_run_envelope() -> None:
    """The first thing run() does is dispatch a properly-shaped RPC envelope."""
    registry = _FakeRegistry(events=_load_sample_events())
    runner = ClaudeCodeRunner(bridge_registry=registry)  # type: ignore[arg-type]

    await runner.run(prompt="hello", session_id="prev-session")

    assert registry.last_target == "mac-1"
    env = registry.last_envelope
    assert env is not None
    assert env["type"] == "command.claude.run"
    assert env["target"] == "mac-1"
    payload = env["payload"]
    assert isinstance(payload, dict)
    assert payload["prompt"] == "hello"
    assert payload["session_id"] == "prev-session"
    assert payload["agent_teams"] is True
    assert payload["permission_mode"] == "acceptEdits"
    # correlation_id and id should match (per Doc 11 §4.2)
    assert env["correlation_id"] == env["id"]
    # ts is an ISO8601 datetime parseable string.
    datetime.fromisoformat(str(env["ts"]).replace("Z", "+00:00"))


@pytest.mark.asyncio
async def test_run_persists_subagent_lifecycle() -> None:
    """spawned event upserts; completed event updates."""
    registry = _FakeRegistry(events=_load_sample_events())
    repo = _FakeSubagentRepo()
    runner = ClaudeCodeRunner(
        bridge_registry=registry,  # type: ignore[arg-type]
        subagent_repo=repo,  # type: ignore[arg-type]
    )

    # Stub _resolve_bridge_uuid so the persistence path doesn't try the DB.
    fake_uuid = uuid.uuid4()

    async def _fake_resolve(_host_id: str) -> uuid.UUID:
        return fake_uuid

    runner._resolve_bridge_uuid = _fake_resolve  # type: ignore[method-assign]

    await runner.run(prompt="ping")

    assert len(repo.upserts) == 1
    upsert = repo.upserts[0]
    assert upsert["bridge_id"] == fake_uuid
    assert upsert["session_id"] == "sess-abc"
    assert upsert["task_id"] == "task-1"
    assert upsert["status"] == "spawned"
    assert upsert["name"] == "alpha"
    assert upsert["prompt_preview"].startswith("Append the exact line")
    assert upsert["subagent_type"] == "general-purpose"
    assert upsert["isolation"] == "worktree"
    assert isinstance(upsert["spawned_at"], datetime)

    assert len(repo.updates) == 1
    update = repo.updates[0]
    assert update["session_id"] == "sess-abc"
    assert update["task_id"] == "task-1"
    assert update["status"] == "completed"
    assert update["summary"] == "README updated"
    assert update["total_tokens"] == 1234
    assert update["tool_uses"] == 3
    assert update["duration_ms"] == 1800
    assert isinstance(update["completed_at"], datetime)


@pytest.mark.asyncio
async def test_run_no_bridge_raises_no_bridge_available() -> None:
    """When no bridge is online the runner raises NoBridgeAvailableError."""
    registry = _FakeRegistry(events=[], online_host=None)
    runner = ClaudeCodeRunner(bridge_registry=registry)  # type: ignore[arg-type]

    with pytest.raises(NoBridgeAvailableError):
        await runner.run(prompt="hello")


@pytest.mark.asyncio
async def test_run_send_failure_raises_claude_code_error() -> None:
    """A failed send_to_bridge surface as a ClaudeCodeError."""
    registry = _FakeRegistry(events=[], send_succeeds=False)
    runner = ClaudeCodeRunner(bridge_registry=registry)  # type: ignore[arg-type]

    with pytest.raises(ClaudeCodeError):
        await runner.run(prompt="hello")


@pytest.mark.asyncio
async def test_run_explicit_bridge_id_used_when_online() -> None:
    """Explicit bridge_id is honoured when the bridge is online."""
    registry = _FakeRegistry(events=_load_sample_events(), online_host="mac-2")
    runner = ClaudeCodeRunner(bridge_registry=registry)  # type: ignore[arg-type]

    await runner.run(prompt="hello", bridge_id="mac-2")

    assert registry.last_target == "mac-2"


@pytest.mark.asyncio
async def test_run_explicit_bridge_id_falls_back_when_offline() -> None:
    """Explicit bridge_id falls through to capability search when offline."""
    registry = _FakeRegistry(events=_load_sample_events(), online_host="mac-1")
    runner = ClaudeCodeRunner(bridge_registry=registry)  # type: ignore[arg-type]

    await runner.run(prompt="hello", bridge_id="ghost-bridge")

    assert registry.last_target == "mac-1"


@pytest.mark.asyncio
async def test_auth_expired_event_raises_claude_code_error() -> None:
    """A bridge.auth_expired event terminates the run with an error."""
    events = [
        {
            "type": "event.session.init",
            "correlation_id": "RPC1",
            "payload": {
                "session_id": "sess-x",
                "model": "claude-opus-4-7",
            },
        },
        {
            "type": "event.bridge.auth_expired",
            "correlation_id": "RPC1",
            "payload": {"reason": "session_revoked"},
        },
    ]
    registry = _FakeRegistry(events=events)
    runner = ClaudeCodeRunner(bridge_registry=registry)  # type: ignore[arg-type]

    with pytest.raises(ClaudeCodeError):
        await runner.run(prompt="hello")


@pytest.mark.asyncio
async def test_run_works_without_optional_callbacks() -> None:
    """All v2.0 callbacks are optional; legacy zero-callback callers must not break."""
    registry = _FakeRegistry(events=_load_sample_events())
    runner = ClaudeCodeRunner(bridge_registry=registry)  # type: ignore[arg-type]

    result = await runner.run(prompt="ping")

    assert result.session_id == "sess-abc"
    assert result.response_text == "Hello world"


@pytest.mark.asyncio
async def test_run_assistant_event_accumulates_response() -> None:
    """An assistant event without prior stream deltas should populate response_text."""
    events = [
        {
            "type": "event.session.init",
            "correlation_id": "RPC1",
            "payload": {"session_id": "s1", "model": "claude-opus-4-7"},
        },
        {
            "type": "event.session.assistant",
            "correlation_id": "RPC1",
            "payload": {
                "session_id": "s1",
                "message": {
                    "content": [{"type": "text", "text": "Result text"}],
                    "usage": {"output_tokens": 42},
                },
            },
        },
        {
            "type": "event.session.result",
            "correlation_id": "RPC1",
            "payload": {
                "session_id": "s1",
                "duration_ms": 100,
                "num_turns": 1,
                "result": "Result text",
                "stop_reason": "end_turn",
                "total_cost_usd": 0.001,
                "model_usage": {
                    "claude-opus-4-7": {
                        "input_tokens": 50,
                        "output_tokens": 42,
                        "cache_read_input_tokens": 0,
                        "cache_creation_input_tokens": 0,
                    }
                },
                "permission_denials": [],
                "terminal_reason": "clean",
            },
        },
    ]
    registry = _FakeRegistry(events=events)
    runner = ClaudeCodeRunner(bridge_registry=registry)  # type: ignore[arg-type]

    deltas: list[str] = []

    async def on_text_delta(text: str, _index: int) -> None:
        deltas.append(text)

    result = await runner.run(prompt="x", on_text_delta=on_text_delta)

    assert result.response_text == "Result text"
    assert deltas == ["Result text"]
    assert result.tokens_output == 42
    assert result.tokens_input == 50


@pytest.mark.asyncio
async def test_subagent_persistence_skipped_when_repo_none() -> None:
    """Without a SubagentRepository, subagent events still fire callbacks but no DB call happens."""
    registry = _FakeRegistry(events=_load_sample_events())
    runner = ClaudeCodeRunner(bridge_registry=registry, subagent_repo=None)  # type: ignore[arg-type]

    spawned: list[dict[str, Any]] = []

    async def on_subagent_spawned(p: dict[str, Any]) -> None:
        spawned.append(p)

    await runner.run(prompt="x", on_subagent_spawned=on_subagent_spawned)

    assert len(spawned) == 1  # callback fires regardless


# ---------------------------------------------------------------------------
# BridgeRegistryService.stream_events / dispatch_event tests.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bridge_registry_dispatch_event_routes_by_correlation_id() -> None:
    """Events with a known correlation_id are placed on the matching subscriber's queue."""
    from app.services.bridge_registry_service import BridgeRegistryService

    svc = BridgeRegistryService()
    rpc_id = "test-rpc-123"

    received: list[dict[str, Any]] = []

    async def consume() -> None:
        async for ev in svc.stream_events(bridge_id="mac-1", rpc_id=rpc_id):
            received.append(ev)
            if ev.get("type") == "event.session.result":
                break

    consumer = asyncio.create_task(consume())
    # Allow the consumer to register its queue.
    await asyncio.sleep(0)

    await svc.dispatch_event(
        {
            "type": "event.session.init",
            "correlation_id": rpc_id,
            "payload": {"session_id": "s1"},
        }
    )
    await svc.dispatch_event(
        {
            "type": "event.session.result",
            "correlation_id": rpc_id,
            "payload": {"session_id": "s1", "result": "done"},
        }
    )

    await consumer
    assert [ev["type"] for ev in received] == [
        "event.session.init",
        "event.session.result",
    ]


@pytest.mark.asyncio
async def test_bridge_registry_dispatch_event_drops_uncorrelated() -> None:
    """Events without a matching subscriber are quietly dropped."""
    from app.services.bridge_registry_service import BridgeRegistryService

    svc = BridgeRegistryService()
    # No subscriber: should be a no-op (not raise).
    await svc.dispatch_event({"type": "event.bridge.alive", "payload": {}})


@pytest.mark.asyncio
async def test_bridge_registry_send_to_bridge_no_manager_returns_false() -> None:
    """Without an injected agent_manager, send_to_bridge returns False."""
    from app.services.bridge_registry_service import BridgeRegistryService

    svc = BridgeRegistryService()
    ok = await svc.send_to_bridge("mac-1", {"type": "command.claude.run"})
    assert ok is False


@pytest.mark.asyncio
async def test_bridge_registry_send_to_bridge_no_connection_returns_false() -> None:
    """If the bridge isn't online, send returns False even with a manager."""
    from unittest.mock import AsyncMock, MagicMock

    from app.services.bridge_registry_service import BridgeRegistryService

    mgr = MagicMock()
    mgr.send_json = AsyncMock(return_value=True)
    svc = BridgeRegistryService(agent_manager=mgr)
    ok = await svc.send_to_bridge("ghost-bridge", {"type": "command.claude.run"})
    assert ok is False


@pytest.mark.asyncio
async def test_runner_default_constructor_uses_singleton() -> None:
    """ClaudeCodeRunner() with no args wires the module-level bridge_registry."""
    runner = ClaudeCodeRunner()
    from app.services.bridge_registry_service import bridge_registry as singleton

    assert runner._bridges is singleton  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_runner_persistence_skipped_when_bridge_uuid_unknown() -> None:
    """If the bridge isn't yet in DB, persistence quietly skips upsert."""
    registry = _FakeRegistry(events=_load_sample_events())
    repo = _FakeSubagentRepo()
    runner = ClaudeCodeRunner(
        bridge_registry=registry,  # type: ignore[arg-type]
        subagent_repo=repo,  # type: ignore[arg-type]
    )

    # Simulate "bridge not in DB" — _resolve_bridge_uuid returns None.
    async def _none_resolver(_host_id: str) -> uuid.UUID | None:
        return None

    runner._resolve_bridge_uuid = _none_resolver  # type: ignore[method-assign]

    await runner.run(prompt="ping")

    assert repo.upserts == []
    # update_subagent_status fires regardless — the row may already exist
    # from a prior bridge-restart scenario.
    assert len(repo.updates) == 1


@pytest.mark.asyncio
async def test_runner_persistence_swallows_upsert_errors() -> None:
    """A repo failure during upsert is logged but does not break the stream."""
    registry = _FakeRegistry(events=_load_sample_events())

    class _BoomRepo:
        upserts: list[dict[str, Any]] = []
        updates: list[dict[str, Any]] = []

        async def upsert_subagent(self, **_kwargs: Any) -> None:
            raise RuntimeError("db down")

        async def update_subagent_status(self, *_args: Any, **_kwargs: Any) -> bool:
            raise RuntimeError("db down")

    runner = ClaudeCodeRunner(
        bridge_registry=registry,  # type: ignore[arg-type]
        subagent_repo=_BoomRepo(),  # type: ignore[arg-type]
    )

    async def _fake_resolve(_host_id: str) -> uuid.UUID:
        return uuid.uuid4()

    runner._resolve_bridge_uuid = _fake_resolve  # type: ignore[method-assign]

    # Should not raise — both errors are swallowed.
    result = await runner.run(prompt="ping")
    assert result.session_id == "sess-abc"


@pytest.mark.asyncio
async def test_runner_skips_persistence_for_blank_session_or_task_id() -> None:
    """Missing identifiers in the spawned/completed payloads bypass persistence."""
    events = [
        {
            "type": "event.session.task_started",
            "correlation_id": "RPC1",
            "payload": {
                # session_id and task_id deliberately empty
                "session_id": "",
                "task_id": "",
                "name": "ghost",
            },
        },
        {
            "type": "event.session.task_notification",
            "correlation_id": "RPC1",
            "payload": {
                "session_id": "",
                "task_id": "",
                "status": "failed",
            },
        },
        {
            "type": "event.session.result",
            "correlation_id": "RPC1",
            "payload": {
                "session_id": "s1",
                "duration_ms": 0,
                "result": "",
                "stop_reason": "end_turn",
                "total_cost_usd": 0,
                "model_usage": {},
                "permission_denials": [],
                "terminal_reason": "ok",
            },
        },
    ]
    registry = _FakeRegistry(events=events)
    repo = _FakeSubagentRepo()
    runner = ClaudeCodeRunner(
        bridge_registry=registry,  # type: ignore[arg-type]
        subagent_repo=repo,  # type: ignore[arg-type]
    )

    async def _fake_resolve(_host_id: str) -> uuid.UUID:
        return uuid.uuid4()

    runner._resolve_bridge_uuid = _fake_resolve  # type: ignore[method-assign]

    await runner.run(prompt="x")

    assert repo.upserts == []
    assert repo.updates == []


@pytest.mark.asyncio
async def test_runner_user_event_is_dropped() -> None:
    """event.session.user echoes (tool_results) are accepted but currently ignored."""
    events = [
        {
            "type": "event.session.user",
            "correlation_id": "RPC1",
            "payload": {"session_id": "s1"},
        },
        {
            "type": "event.session.result",
            "correlation_id": "RPC1",
            "payload": {
                "session_id": "s1",
                "duration_ms": 1,
                "result": "ok",
                "stop_reason": "end_turn",
                "total_cost_usd": 0,
                "model_usage": {},
                "permission_denials": [],
                "terminal_reason": "ok",
            },
        },
    ]
    registry = _FakeRegistry(events=events)
    runner = ClaudeCodeRunner(bridge_registry=registry)  # type: ignore[arg-type]
    result = await runner.run(prompt="x")
    assert result.response_text == "ok"


@pytest.mark.asyncio
async def test_runner_unknown_event_type_is_ignored() -> None:
    """An unrecognised event.type is logged + skipped, never crashes the stream."""
    events = [
        {
            "type": "event.session.does_not_exist",
            "correlation_id": "RPC1",
            "payload": {},
        },
        {
            "type": "event.session.result",
            "correlation_id": "RPC1",
            "payload": {
                "session_id": "s1",
                "duration_ms": 1,
                "result": "fine",
                "stop_reason": "end_turn",
                "total_cost_usd": 0,
                "model_usage": {},
                "permission_denials": [],
                "terminal_reason": "ok",
            },
        },
    ]
    registry = _FakeRegistry(events=events)
    runner = ClaudeCodeRunner(bridge_registry=registry)  # type: ignore[arg-type]
    result = await runner.run(prompt="x")
    assert result.response_text == "fine"


@pytest.mark.asyncio
async def test_runner_cancel_is_noop() -> None:
    """v2.0 cancel() is intentionally a no-op until command.claude.abort lands."""
    runner = ClaudeCodeRunner()
    await runner.cancel()  # must not raise


# ---------------------------------------------------------------------------
# Helper-function tests (parsing utilities).
# ---------------------------------------------------------------------------


def test_extract_delta_text_handles_text_delta_shape() -> None:
    """Top-level text_delta payload returns its `text` field."""
    from app.orchestrator.claude_code_runner import _extract_delta_text

    assert _extract_delta_text({"type": "text_delta", "text": "hi"}) == "hi"


def test_extract_delta_text_handles_nested_delta() -> None:
    """A nested ``delta`` envelope is followed transitively."""
    from app.orchestrator.claude_code_runner import _extract_delta_text

    nested = {"delta": {"type": "text_delta", "text": "deep"}}
    assert _extract_delta_text(nested) == "deep"


def test_extract_delta_text_handles_content_block_envelope() -> None:
    """A content_block_delta envelope is unwrapped."""
    from app.orchestrator.claude_code_runner import _extract_delta_text

    block = {"content_block_delta": {"type": "text_delta", "text": "block"}}
    assert _extract_delta_text(block) == "block"


def test_extract_delta_text_returns_empty_for_unknown_shape() -> None:
    """Unrecognised shapes return an empty string."""
    from app.orchestrator.claude_code_runner import _extract_delta_text

    assert _extract_delta_text({"type": "image_delta"}) == ""
    assert _extract_delta_text("not a dict") == ""


def test_extract_assistant_text_decodes_json_string() -> None:
    """A JSON-encoded string message is parsed and its text extracted."""
    from app.orchestrator.claude_code_runner import _extract_assistant_text_and_tokens

    payload = json.dumps({"content": [{"type": "text", "text": "hi"}]})
    text, tokens = _extract_assistant_text_and_tokens(payload)
    assert text == "hi"
    assert tokens == 0


def test_extract_assistant_text_returns_zero_on_invalid_json() -> None:
    """A non-JSON string returns the empty pair."""
    from app.orchestrator.claude_code_runner import _extract_assistant_text_and_tokens

    text, tokens = _extract_assistant_text_and_tokens("definitely not json")
    assert (text, tokens) == ("", 0)


def test_extract_assistant_text_rejects_unsupported_type() -> None:
    """Numbers and other non-message types yield the empty pair."""
    from app.orchestrator.claude_code_runner import _extract_assistant_text_and_tokens

    assert _extract_assistant_text_and_tokens(42) == ("", 0)


def test_stringify_optional_handles_all_input_kinds() -> None:
    """None passes through, empty string normalises to None, ints stringify."""
    from app.orchestrator.claude_code_runner import _stringify_optional

    assert _stringify_optional(None) is None
    assert _stringify_optional("") is None
    assert _stringify_optional("hi") == "hi"
    assert _stringify_optional(42) == "42"


def test_optional_int_handles_all_input_kinds() -> None:
    """None, ints, floats, parsable + unparsable strings, and rejects garbage."""
    from app.orchestrator.claude_code_runner import _optional_int

    assert _optional_int(None) is None
    assert _optional_int(7) == 7
    assert _optional_int(1.5) == 1
    assert _optional_int(True) == 1
    assert _optional_int("42") == 42
    assert _optional_int("nope") is None
    assert _optional_int(object()) is None


def test_parse_iso_uses_default_when_value_invalid() -> None:
    """Malformed timestamps fall back to the default."""
    from app.orchestrator.claude_code_runner import _parse_iso

    default_iso = "2026-05-02T12:00:00+00:00"
    out = _parse_iso("not-a-date", default=default_iso)
    assert out == datetime.fromisoformat(default_iso)


def test_parse_iso_handles_z_suffix() -> None:
    """A trailing Z is normalised to +00:00."""
    from app.orchestrator.claude_code_runner import _parse_iso

    out = _parse_iso("2026-05-02T10:00:00Z", default="2026-05-02T00:00:00+00:00")
    assert out.year == 2026
    assert out.hour == 10
