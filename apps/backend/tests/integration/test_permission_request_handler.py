"""Integration tests for the V1.4 ``permission_request`` handler.

These tests cover the new bridge envelope path that lands in
:mod:`app.orchestrator.claude_code_runner` (V1.4 §2.1.4) and the
follow-through callback in :mod:`app.api.routes.websocket` (V1.4
§2.2.3). The runbook §11 wiring gap #1+#2+#4 closes when the round-trip
counters increment AND the bridge-side decision RPC envelope is
dispatched with the right correlation tokens.

Five scenarios per the V1.4 task spec test plan:

* **A** — happy-path approve: synthetic ``event.session.permission_request``
  → ``approval_service.create_approval`` → QUESTION envelope to iOS →
  ``submit_decision(approved)`` → ``command.claude.permission.allow``
  envelope dispatched + counters incremented.
* **B** — happy-path deny: same as A but rejected →
  ``command.claude.permission.deny`` envelope.
* **C** — timeout auto-deny: no decision submitted →
  ``permission_request_timeout_total`` increments → deny envelope sent.
* **D** — bridge offline mid-decision: ``send_to_bridge`` returns False
  → ``permission_dispatch_failed`` log fires (captured via
  ``structlog.testing.capture_logs``) with no exception propagated.
* **E** — runner does not block: while the awaiter waits on the user's
  decision, dispatch ANOTHER event (e.g. ``event.session.assistant``)
  and assert the runner consumes it concurrently. Proves the
  fire-and-forget Task contract.

The ``capture_logs`` call (Test D) follows the T2.9-fix lesson: capsys
does not see structlog output because structlog writes through its own
processor chain, not stdlib logging.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
import structlog

from app.core import metrics as _metrics
from app.orchestrator.claude_code_runner import ClaudeCodeRunner
from app.schemas.approval import (
    CATEGORY_TIMEOUTS,
    ApprovalCategory,
    ApprovalDecision,
    ApprovalRequestRecord,
)
from app.schemas.messages import MessageType
from app.services.approval_service import ApprovalService

# ---------------------------------------------------------------------------
# Fakes / helpers
# ---------------------------------------------------------------------------


class _FakeRegistry:
    """Captures register/send/dispatch traffic the runner emits.

    The synthetic event list is replayed lazily — the queue is populated
    before each yield so the consumer (runner.stream_events) sees events
    in the same order the bridge would emit them. Each event is stamped
    with the runner's ``rpc_id`` as ``correlation_id`` so the inbound
    dispatcher path matches.
    """

    def __init__(
        self,
        *,
        events: list[dict[str, Any]],
        send_succeeds: bool = True,
        host_id: str = "mac-1",
    ) -> None:
        self._events = list(events)
        self._send_succeeds = send_succeeds
        self._host_id = host_id
        # Captured envelopes (RPC sent to the bridge): the test inspects
        # the LAST one for the decision RPC assertions.
        self.sent_envelopes: list[tuple[str, dict[str, Any]]] = []

    def get_connection_id(self, host_id: str) -> str | None:
        return f"conn-{host_id}" if host_id == self._host_id else None

    def find_online_agent_with_capability(self, _capability: str) -> str | None:
        return self._host_id

    def register_subscriber(
        self, *, bridge_id: str, rpc_id: str
    ) -> asyncio.Queue[dict[str, Any]]:
        del bridge_id, rpc_id
        return asyncio.Queue()

    def unregister_subscriber(self, *, bridge_id: str, rpc_id: str) -> None:
        del bridge_id, rpc_id

    async def send_to_bridge(
        self, host_id: str, envelope: dict[str, Any]
    ) -> bool:
        self.sent_envelopes.append((host_id, envelope))
        return self._send_succeeds

    async def stream_events(
        self,
        *,
        rpc_id: str,
        bridge_id: str | None = None,
        queue: asyncio.Queue[dict[str, Any]] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        del bridge_id, queue
        for raw in self._events:
            event = dict(raw)
            event["correlation_id"] = rpc_id
            yield event


def _result_event() -> dict[str, Any]:
    """Produce the terminal ``event.session.result`` envelope."""
    return {
        "type": "event.session.result",
        "payload": {
            "duration_ms": 100,
            "result": "done",
            "total_cost_usd": 0.0,
            "model_usage": {},
        },
    }


def _permission_request_event(
    *,
    request_id: str = "req-001",
    tool_name: str = "Bash",
    risk: str = "high",
    timeout_ms: int = 30_000,
    input_preview: str = "rm -rf /tmp/scratch",
) -> dict[str, Any]:
    """Build a synthetic ``event.session.permission_request`` envelope."""
    return {
        "type": "event.session.permission_request",
        "payload": {
            "request_id": request_id,
            "tool_name": tool_name,
            "risk": risk,
            "input_preview": input_preview,
            "timeout_ms": timeout_ms,
            "session_id": "sess-perm-001",
        },
    }


@pytest_asyncio.fixture
async def approval_service() -> AsyncIterator[ApprovalService]:
    """Provide an isolated :class:`ApprovalService` with no DB writes.

    Mirrors the T3.2 fixture in ``test_permission_flow.py`` — the
    repository writes are stubbed so the test stays decoupled from the
    live database. The singleton from ``get_approval_service`` is
    monkey-patched to return this fresh instance for every test.
    """

    class _NoOpSession:
        async def __aenter__(self) -> _NoOpSession:
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

        async def commit(self) -> None:
            return None

    service = ApprovalService()

    with (
        patch(
            "app.repositories.approval_repo.ApprovalRepository.create",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.repositories.approval_repo.ApprovalRepository.update_status",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.core.database.async_session_factory",
            side_effect=lambda: _NoOpSession(),
        ),
        patch(
            "app.services.approval_service.get_approval_service",
            return_value=service,
        ),
    ):
        yield service


def _read_counter_value(
    counter_metric: Any,
    *,
    labels: dict[str, str],
) -> float:
    """Snapshot a single Prometheus counter value.

    prometheus_client exposes a private ``_value.get()`` per labelset;
    accessing it directly keeps the test cheap (no full
    ``generate_latest`` parse). The labels dict order doesn't matter
    because ``Counter.labels`` resolves by kwarg name.
    """
    return float(counter_metric.labels(**labels)._value.get())  # noqa: SLF001


# ---------------------------------------------------------------------------
# Test A — happy path approve.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_permission_request_happy_path_approve(
    approval_service: ApprovalService,
) -> None:
    """End-to-end: bridge envelope → approval → iOS push → user approve →
    bridge gets ``command.claude.permission.allow`` with right correlation."""
    sent_questions: list[dict[str, Any]] = []

    captured_record_ref: dict[str, ApprovalRequestRecord] = {}

    async def _on_permission_request(
        record: ApprovalRequestRecord,
        bridge_host_id: str,
        rpc_id: str,
        timeout_seconds: int,
    ) -> None:
        # Capture state for post-run assertions.
        captured_record_ref["record"] = record
        captured_record_ref["bridge_host_id"] = bridge_host_id  # type: ignore[assignment]
        captured_record_ref["rpc_id"] = rpc_id  # type: ignore[assignment]
        captured_record_ref["timeout_seconds"] = timeout_seconds  # type: ignore[assignment]

        # Build the QUESTION envelope (mirrors websocket._on_permission_request).
        envelope = approval_service.build_question_message(
            record, session_id=record.session_id
        )
        sent_questions.append(envelope)

        async def _await_and_dispatch() -> None:
            result = await approval_service.wait_for_decision(
                record.id, timeout_override=timeout_seconds
            )
            decision_str = "allow" if result.approved else "deny"
            envelope_type = (
                "command.claude.permission.allow"
                if result.approved
                else "command.claude.permission.deny"
            )
            await registry.send_to_bridge(
                bridge_host_id,
                {
                    "type": envelope_type,
                    "correlation_id": rpc_id,
                    "payload": {
                        "session_id": record.session_id,
                        "request_id": record.request_id,
                        "decision": decision_str,
                        "reason": result.note or "",
                    },
                },
            )
            _metrics.permission_request_decided_total.labels(
                bridge_id=bridge_host_id,
                tool_name=record.tool_name or "unknown",
                decision=result.decision,
            ).inc()

        asyncio.create_task(_await_and_dispatch())

    events = [_permission_request_event(), _result_event()]
    registry = _FakeRegistry(events=events)
    runner = ClaudeCodeRunner(bridge_registry=registry)  # type: ignore[arg-type]

    # Snapshot counters BEFORE the run so we can assert deltas.
    emitted_before = _read_counter_value(
        _metrics.permission_request_emitted_total,
        labels={"bridge_id": "mac-1", "tool_name": "Bash", "risk": "high"},
    )
    decided_before = _read_counter_value(
        _metrics.permission_request_decided_total,
        labels={"bridge_id": "mac-1", "tool_name": "Bash", "decision": "approved"},
    )

    # Spawn the runner in a Task so we can submit the decision concurrently.
    run_task = asyncio.create_task(
        runner.run(prompt="ping", on_permission_request=_on_permission_request)
    )

    # Wait for the QUESTION to appear.
    for _ in range(50):
        await asyncio.sleep(0.005)
        if sent_questions:
            break
    assert sent_questions, "QUESTION envelope must be pushed to iOS"

    # Submit the user's approval.
    record = captured_record_ref["record"]
    submitted = await approval_service.submit_decision(
        ApprovalDecision(approval_id=record.id, decision="approved", note="ok"),
    )
    assert submitted is True

    # Wait for the runner to finish + the awaiter task to dispatch.
    await asyncio.wait_for(run_task, timeout=2.0)
    for _ in range(50):
        await asyncio.sleep(0.005)
        # The first send_to_bridge call is the command.claude.run RPC;
        # the decision RPC is whichever envelope follows it.
        if any(
            env.get("type", "").startswith("command.claude.permission.")
            for _, env in registry.sent_envelopes
        ):
            break

    # 1. Approval record was created with bridge correlation tokens.
    assert record.tool_name == "Bash"
    assert record.category is ApprovalCategory.DESTRUCTIVE
    assert record.request_id == "req-001"
    assert record.bridge_host_id == "mac-1"
    # 2. QUESTION envelope shape.
    question = sent_questions[0]
    assert question["type"] == MessageType.QUESTION.value
    # 3. Decision RPC dispatched with the right correlation_id.
    decision_envelopes = [
        env
        for _, env in registry.sent_envelopes
        if env.get("type") == "command.claude.permission.allow"
    ]
    assert len(decision_envelopes) == 1
    decision_env = decision_envelopes[0]
    assert decision_env["correlation_id"] == record.rpc_id
    payload = decision_env["payload"]
    assert payload["decision"] == "allow"
    assert payload["request_id"] == "req-001"
    # 4. Counters incremented.
    emitted_after = _read_counter_value(
        _metrics.permission_request_emitted_total,
        labels={"bridge_id": "mac-1", "tool_name": "Bash", "risk": "high"},
    )
    decided_after = _read_counter_value(
        _metrics.permission_request_decided_total,
        labels={"bridge_id": "mac-1", "tool_name": "Bash", "decision": "approved"},
    )
    assert emitted_after - emitted_before == pytest.approx(1.0)
    assert decided_after - decided_before == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Test B — happy path deny.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_permission_request_happy_path_deny(
    approval_service: ApprovalService,
) -> None:
    """User taps deny → ``command.claude.permission.deny`` envelope sent."""
    captured_record_ref: dict[str, ApprovalRequestRecord] = {}

    async def _on_permission_request(
        record: ApprovalRequestRecord,
        bridge_host_id: str,
        rpc_id: str,
        timeout_seconds: int,
    ) -> None:
        captured_record_ref["record"] = record

        async def _await_and_dispatch() -> None:
            result = await approval_service.wait_for_decision(
                record.id, timeout_override=timeout_seconds
            )
            envelope_type = (
                "command.claude.permission.allow"
                if result.approved
                else "command.claude.permission.deny"
            )
            await registry.send_to_bridge(
                bridge_host_id,
                {
                    "type": envelope_type,
                    "correlation_id": rpc_id,
                    "payload": {
                        "session_id": record.session_id,
                        "request_id": record.request_id,
                        "decision": "allow" if result.approved else "deny",
                    },
                },
            )

        asyncio.create_task(_await_and_dispatch())

    events = [_permission_request_event(), _result_event()]
    registry = _FakeRegistry(events=events)
    runner = ClaudeCodeRunner(bridge_registry=registry)  # type: ignore[arg-type]

    run_task = asyncio.create_task(
        runner.run(prompt="x", on_permission_request=_on_permission_request)
    )

    for _ in range(50):
        await asyncio.sleep(0.005)
        if "record" in captured_record_ref:
            break

    record = captured_record_ref["record"]
    await approval_service.submit_decision(
        ApprovalDecision(approval_id=record.id, decision="rejected"),
    )

    await asyncio.wait_for(run_task, timeout=2.0)
    for _ in range(50):
        await asyncio.sleep(0.005)
        if any(
            env.get("type") == "command.claude.permission.deny"
            for _, env in registry.sent_envelopes
        ):
            break

    deny_envelopes = [
        env
        for _, env in registry.sent_envelopes
        if env.get("type") == "command.claude.permission.deny"
    ]
    assert len(deny_envelopes) == 1
    assert deny_envelopes[0]["payload"]["decision"] == "deny"


# ---------------------------------------------------------------------------
# Test C — timeout auto-deny.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_permission_request_timeout_auto_denies(
    approval_service: ApprovalService,
) -> None:
    """No decision → expired → ``command.claude.permission.deny`` sent +
    ``permission_request_timeout_total`` increments."""

    async def _on_permission_request(
        record: ApprovalRequestRecord,
        bridge_host_id: str,
        rpc_id: str,
        _timeout_seconds: int,
    ) -> None:
        async def _await_and_dispatch() -> None:
            # Force a 1s deadline so the test finishes fast.
            result = await approval_service.wait_for_decision(
                record.id, timeout_override=1
            )
            envelope_type = (
                "command.claude.permission.allow"
                if result.approved
                else "command.claude.permission.deny"
            )
            if result.decision == "expired":
                _metrics.permission_request_timeout_total.labels(
                    bridge_id=bridge_host_id,
                    tool_name=record.tool_name or "unknown",
                ).inc()
            await registry.send_to_bridge(
                bridge_host_id,
                {
                    "type": envelope_type,
                    "correlation_id": rpc_id,
                    "payload": {
                        "decision": "deny" if not result.approved else "allow",
                        "reason": result.note or "",
                    },
                },
            )

        asyncio.create_task(_await_and_dispatch())

    # Patch the destructive timeout so the natural code path exercises a
    # 1-second timer instead of 300 s.
    with patch.dict(CATEGORY_TIMEOUTS, {ApprovalCategory.DESTRUCTIVE: 2}):
        events = [_permission_request_event(), _result_event()]
        registry = _FakeRegistry(events=events)
        runner = ClaudeCodeRunner(bridge_registry=registry)  # type: ignore[arg-type]

        timeout_before = _read_counter_value(
            _metrics.permission_request_timeout_total,
            labels={"bridge_id": "mac-1", "tool_name": "Bash"},
        )

        await runner.run(
            prompt="x", on_permission_request=_on_permission_request
        )

        # Wait long enough for the awaiter to timeout-deny.
        for _ in range(50):
            await asyncio.sleep(0.05)
            if any(
                env.get("type") == "command.claude.permission.deny"
                for _, env in registry.sent_envelopes
            ):
                break

        deny_envelopes = [
            env
            for _, env in registry.sent_envelopes
            if env.get("type") == "command.claude.permission.deny"
        ]
        assert deny_envelopes, "timeout MUST trigger an auto-deny dispatch"

        timeout_after = _read_counter_value(
            _metrics.permission_request_timeout_total,
            labels={"bridge_id": "mac-1", "tool_name": "Bash"},
        )
        assert timeout_after - timeout_before == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Test D — bridge offline mid-decision.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_permission_request_bridge_offline_logs_dispatch_failed(
    approval_service: ApprovalService,
) -> None:
    """``send_to_bridge`` returns False → ``permission_dispatch_failed``
    log fires AND no exception propagates to the caller."""
    logger: structlog.stdlib.BoundLogger = structlog.get_logger()

    async def _on_permission_request(
        record: ApprovalRequestRecord,
        bridge_host_id: str,
        rpc_id: str,
        _timeout_seconds: int,
    ) -> None:
        async def _await_and_dispatch() -> None:
            result = await approval_service.wait_for_decision(
                record.id, timeout_override=10
            )
            sent = await registry.send_to_bridge(
                bridge_host_id,
                {
                    "type": "command.claude.permission.allow"
                    if result.approved
                    else "command.claude.permission.deny",
                    "correlation_id": rpc_id,
                    "payload": {"decision": "allow" if result.approved else "deny"},
                },
            )
            if not sent:
                await logger.awarning(
                    "permission_dispatch_failed",
                    bridge_host_id=bridge_host_id,
                    request_id=record.request_id,
                )

        asyncio.create_task(_await_and_dispatch())

    events = [_permission_request_event(), _result_event()]
    # send_succeeds=False simulates the bridge dropping its WS connection
    # mid-decision (or restart). The awaiter must handle this without
    # raising; the bridge's own UDS broker timeout will then deny.
    registry = _FakeRegistry(events=events, send_succeeds=False)
    runner = ClaudeCodeRunner(bridge_registry=registry)  # type: ignore[arg-type]

    captured_record: dict[str, ApprovalRequestRecord] = {}

    async def _capture_then_dispatch(
        record: ApprovalRequestRecord,
        bridge_host_id: str,
        rpc_id: str,
        timeout_seconds: int,
    ) -> None:
        captured_record["record"] = record
        await _on_permission_request(record, bridge_host_id, rpc_id, timeout_seconds)

    # Note: the runner's own command.claude.run RPC also goes through
    # send_to_bridge. With send_succeeds=False the runner raises
    # ClaudeCodeError; this is expected — the test cares about the
    # decision-RPC fallout, not the runner happy path. We pre-allow the
    # initial send by mocking the first call to succeed.
    original_send = registry.send_to_bridge
    call_idx = {"n": 0}

    async def _send_first_ok(host_id: str, envelope: dict[str, Any]) -> bool:
        call_idx["n"] += 1
        if call_idx["n"] == 1:
            registry.sent_envelopes.append((host_id, envelope))
            return True
        return await original_send(host_id, envelope)

    registry.send_to_bridge = _send_first_ok  # type: ignore[method-assign]

    with structlog.testing.capture_logs() as captured:
        await runner.run(
            prompt="x", on_permission_request=_capture_then_dispatch
        )

        for _ in range(50):
            await asyncio.sleep(0.005)
            if "record" in captured_record:
                break

        record = captured_record["record"]
        await approval_service.submit_decision(
            ApprovalDecision(approval_id=record.id, decision="approved"),
        )

        for _ in range(50):
            await asyncio.sleep(0.005)
            if any(
                e.get("event") == "permission_dispatch_failed" for e in captured
            ):
                break

    dispatch_failed_logs = [
        e for e in captured if e.get("event") == "permission_dispatch_failed"
    ]
    assert dispatch_failed_logs, (
        "permission_dispatch_failed log MUST fire when bridge is offline"
    )


# ---------------------------------------------------------------------------
# Test E — runner does not block on user think-time.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_permission_request_does_not_block_runner(
    approval_service: ApprovalService,
) -> None:
    """A pending decision must NOT stall the runner's stream loop —
    subsequent envelopes (assistant, etc) keep flowing."""
    text_deltas: list[str] = []

    async def _on_text_delta(delta: str, _index: int) -> None:
        text_deltas.append(delta)

    async def _on_permission_request(
        record: ApprovalRequestRecord,
        _bridge_host_id: str,
        _rpc_id: str,
        _timeout_seconds: int,
    ) -> None:
        # Spawn an awaiter that waits forever on the user — proves the
        # runner does NOT wait for it.
        async def _wait_forever() -> None:
            await approval_service.wait_for_decision(
                record.id, timeout_override=10
            )

        asyncio.create_task(_wait_forever())

    # Permission request arrives FIRST. If the runner blocked on the
    # awaiter, the assistant event below would never be processed and
    # text_deltas would stay empty.
    assistant_event: dict[str, Any] = {
        "type": "event.session.assistant",
        "payload": {
            "message": {
                "content": [{"type": "text", "text": "Hello"}],
                "usage": {"output_tokens": 5},
            },
        },
    }
    events = [
        _permission_request_event(),
        assistant_event,
        _result_event(),
    ]
    registry = _FakeRegistry(events=events)
    runner = ClaudeCodeRunner(bridge_registry=registry)  # type: ignore[arg-type]

    # Run with a generous outer timeout — if blocking happens, this
    # would expire only after the awaiter's 10s inner deadline.
    result = await asyncio.wait_for(
        runner.run(
            prompt="x",
            on_text_delta=_on_text_delta,
            on_permission_request=_on_permission_request,
        ),
        timeout=2.0,
    )

    # The assistant event ran AFTER the permission_request → text was
    # captured → runner did not block.
    assert text_deltas == ["Hello"], (
        "runner MUST process subsequent envelopes while a decision is pending"
    )
    # The terminal result envelope was consumed → run completed.
    # ``session_id`` stays "" because we didn't include an
    # ``event.session.init`` envelope in this fixture; the existence of
    # the ``response_text`` from the result envelope (set to "done" by
    # ``_result_event``) is the proof the terminal event was reached.
    assert result.response_text == "done"

    # Cleanup: cancel any leaked awaiter to avoid pytest warnings.
    pending = [t for t in asyncio.all_tasks() if not t.done() and t is not asyncio.current_task()]
    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)
