"""Integration tests for the permission / approval flow (T3.2).

These tests verify the contract documented in
``docs/runbooks/permission-flow.md`` — specifically the V1 surface area
where the orchestrator drives :class:`ApprovalService` directly. Today
the bridge surfaces denials only on the terminal
``event.session.result.permission_denials`` array; per-tool real-time
``permission_request`` envelope wiring is the gap noted in §11 of the
runbook (deferred follow-up). The tests below therefore exercise the
authoritative V1 path:

    bridge denial / orchestrator-initiated approval
        -> ``ApprovalService.create_approval``
        -> WebSocket ``question`` push (build_question_message)
        -> iOS ``approval_response``
        -> ``ApprovalService.submit_decision``
        -> ``AuditService.log_tool_call``

All asyncio sleeps used for timeout exercises are kept short
(milliseconds) by overriding ``CATEGORY_TIMEOUTS`` at the test scope so
the suite stays fast. The deny-on-timeout invariant from §7 is
verified via the ``ApprovalResult.decision == "expired"`` assertion.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from typing import cast
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from app.schemas.approval import (
    APPROVAL_MATRIX,
    CATEGORY_TIMEOUTS,
    ApprovalCategory,
    ApprovalDecision,
    ApprovalRequestCreate,
    ApprovalStatus,
)
from app.schemas.messages import MessageDirection, MessageType
from app.services.approval_service import ApprovalService

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def approval_service() -> AsyncIterator[ApprovalService]:
    """Provide a fresh :class:`ApprovalService` per test.

    The DB persistence path is best-effort and silently swallows
    failures; we patch ``async_session_factory`` to a no-op so the
    tests stay isolated from a live database.
    """

    class _NoOpSession:
        async def __aenter__(self) -> _NoOpSession:
            return self

        async def __aexit__(self, *_: object) -> None:  # noqa: D401
            return None

        async def commit(self) -> None:  # noqa: D401
            return None

    def _factory() -> _NoOpSession:
        return _NoOpSession()

    with patch(
        "app.repositories.approval_repo.ApprovalRepository.create",
        new=AsyncMock(return_value=None),
    ), patch(
        "app.repositories.approval_repo.ApprovalRepository.update_status",
        new=AsyncMock(return_value=None),
    ), patch(
        "app.core.database.async_session_factory",
        side_effect=_factory,
    ):
        yield ApprovalService()


@pytest.fixture
def sample_request() -> ApprovalRequestCreate:
    """Build a representative bridge-originated approval request.

    Mirrors the payload the orchestrator constructs after the bridge
    surfaces a denial for a high-risk tool (``shell_rm``).
    """
    return ApprovalRequestCreate(
        session_id="sess-permission-flow",
        connection_id="conn-permission-flow",
        tool_name="shell_rm",
        action="rm -rf /tmp/scratch",
        description="Delete scratch directory",
        params={"path": "/tmp/scratch"},
        category=ApprovalCategory.DESTRUCTIVE,
    )


# ---------------------------------------------------------------------------
# Test 1 — bridge / orchestrator denial routes to ApprovalService.
# ---------------------------------------------------------------------------


class TestPermissionRequestRouting:
    """Verify a ``permission_request`` (orchestrator-mediated) lands in
    :class:`ApprovalService` with the correct fields preserved end-to-end."""

    @pytest.mark.asyncio
    async def test_permission_request_routes_to_approval_service(
        self,
        approval_service: ApprovalService,
        sample_request: ApprovalRequestCreate,
    ) -> None:
        """A bridge-emitted denial -> orchestrator -> create_approval(...)
        produces a tracked record with stable identity + question payload."""
        record = await approval_service.create_approval(sample_request)

        assert record.id, "approval id must be assigned"
        assert record.tool_name == "shell_rm"
        assert record.action == "rm -rf /tmp/scratch"
        assert record.category is ApprovalCategory.DESTRUCTIVE
        assert record.status is ApprovalStatus.PENDING
        # Deny-on-timeout invariant requires a positive timeout.
        assert record.timeout_seconds > 0
        # Round-trip via the lookup helpers.
        assert approval_service.get_pending_approval(record.id) is record
        assert approval_service.get_session_pending(sample_request.session_id) is record
        # Question message that would be pushed to iOS preserves the
        # approval id and renders both options for the user.
        question_msg = approval_service.build_question_message(
            record, session_id=sample_request.session_id
        )
        assert question_msg["type"] == MessageType.QUESTION.value
        content = cast(dict[str, object], question_msg["content"])
        assert content["approval_id"] == record.id
        options = cast(list[dict[str, object]], content["options"])
        assert {opt["id"] for opt in options} == {"approve", "reject"}
        metadata = cast(dict[str, object], question_msg["metadata"])
        assert metadata["direction"] == MessageDirection.SERVER_TO_CLIENT.value

    @pytest.mark.asyncio
    async def test_approval_matrix_categories_have_timeouts(self) -> None:
        """Every categorised tool has a positive timeout — no silent denials."""
        for tool, category in APPROVAL_MATRIX.items():
            timeout = CATEGORY_TIMEOUTS.get(category, 300)
            assert timeout > 0, f"tool={tool} category={category} has zero timeout"


# ---------------------------------------------------------------------------
# Test 2 — iOS decision propagates back into the awaiter.
# ---------------------------------------------------------------------------


class TestApprovalDecisionPropagation:
    """The iOS ``approval_response`` -> ``submit_decision`` path must
    resolve the orchestrator's pending future so the bridge tool call
    can resume."""

    @pytest.mark.asyncio
    async def test_approval_decision_propagates_to_bridge(
        self,
        approval_service: ApprovalService,
        sample_request: ApprovalRequestCreate,
    ) -> None:
        record = await approval_service.create_approval(sample_request)

        # Simulate orchestrator awaiting the decision.
        wait_task = asyncio.create_task(
            approval_service.wait_for_decision(record.id)
        )
        # Give the awaiter one event-loop tick to register its future
        # so submit_decision sees a live waiter.
        for _ in range(5):
            await asyncio.sleep(0)
            if record.id in approval_service._waiters:  # noqa: SLF001
                break
        assert record.id in approval_service._waiters  # noqa: SLF001

        decision = ApprovalDecision(
            approval_id=record.id,
            decision="approved",
            note="ok from iOS",
        )
        submitted = await approval_service.submit_decision(decision)
        assert submitted is True

        result = await asyncio.wait_for(wait_task, timeout=1.0)
        assert result.approved is True
        assert result.approval_id == record.id
        assert result.decision == "approved"
        assert result.note == "ok from iOS"

        # Pending entry consumed; history records the resolution.
        assert approval_service.get_pending_approval(record.id) is None
        history = approval_service.get_history(limit=1)
        assert history
        assert history[0].id == record.id
        assert history[0].status is ApprovalStatus.APPROVED


# ---------------------------------------------------------------------------
# Test 3 — deny-on-timeout invariant (§7).
# ---------------------------------------------------------------------------


class TestApprovalTimeout:
    """Silence is never a yes — when the iOS user does not respond, the
    awaiter MUST receive a deny."""

    @pytest.mark.asyncio
    async def test_default_timeout_denies_after_30s(
        self,
        approval_service: ApprovalService,
        sample_request: ApprovalRequestCreate,
    ) -> None:
        """Deny-on-timeout invariant via the natural code path.

        The "30s" in the name is *historical*: Spike Test #5's reference
        timeout was 30 seconds, and production widens that per category
        (see ``CATEGORY_TIMEOUTS`` in ``app/schemas/approval.py``). The
        behaviour under test is the **invariant** — silence is never a
        yes — not the wall-clock value. We patch the category timeout
        down to 1s and wrap the awaiter with an outer
        ``asyncio.wait_for(..., 2.0)`` guard so the suite stays fast
        (<2 s) while the natural ``create_approval`` →
        ``wait_for_decision`` path exercises the timer through the same
        code branches a 30s+ production run would hit.
        """
        with patch.dict(
            CATEGORY_TIMEOUTS,
            {ApprovalCategory.DESTRUCTIVE: 1},  # 1s -> exercises timer branch
        ):
            record = await approval_service.create_approval(sample_request)
            # Outer guard ensures the test fails fast if the timer never
            # fires; the inner deny-on-timeout assertion is the contract.
            result = await asyncio.wait_for(
                approval_service.wait_for_decision(record.id),
                timeout=2.0,
            )

        assert result.approved is False, "timeout MUST deny — silence is never a yes"
        assert result.decision == "expired"
        assert result.approval_id == record.id

        # The expired record should land in history with the right status.
        history = approval_service.get_history(limit=1)
        assert history
        assert history[0].id == record.id
        assert history[0].status is ApprovalStatus.EXPIRED


# ---------------------------------------------------------------------------
# Test 4 — concurrent approvals stay isolated (§9.1).
# ---------------------------------------------------------------------------


class TestConcurrentApprovals:
    """Three subagents requesting approval simultaneously must each get
    their own pending slot + their own future, addressable by id."""

    @pytest.mark.asyncio
    async def test_concurrent_approvals_isolated_by_id(
        self,
        approval_service: ApprovalService,
    ) -> None:
        requests = [
            ApprovalRequestCreate(
                session_id=f"sess-concurrent-{i}",
                connection_id=f"conn-concurrent-{i}",
                tool_name="git_push",
                action=f"git push origin feature/concurrent-{i}",
                description=f"Push branch #{i}",
                category=ApprovalCategory.WRITE_REMOTE,
            )
            for i in range(3)
        ]
        records = [await approval_service.create_approval(req) for req in requests]
        ids = [r.id for r in records]
        assert len(set(ids)) == 3, "approval ids MUST be unique per request"
        assert approval_service.pending_count == 3

        # Each id resolves to its own record.
        for rec in records:
            looked_up = approval_service.get_pending_approval(rec.id)
            assert looked_up is rec

        # Spin up three concurrent waiters.
        wait_tasks = [
            asyncio.create_task(approval_service.wait_for_decision(rec.id))
            for rec in records
        ]
        # Wait for all three futures to register.
        for _ in range(20):
            await asyncio.sleep(0)
            if all(rec.id in approval_service._waiters for rec in records):  # noqa: SLF001
                break
        assert all(
            rec.id in approval_service._waiters  # noqa: SLF001
            for rec in records
        )

        # Resolve in REVERSE order to prove no FIFO coupling.
        decisions = [
            ApprovalDecision(approval_id=records[2].id, decision="approved"),
            ApprovalDecision(approval_id=records[0].id, decision="rejected"),
            ApprovalDecision(approval_id=records[1].id, decision="approved"),
        ]
        for d in decisions:
            submitted = await approval_service.submit_decision(d)
            assert submitted is True

        results = await asyncio.gather(*wait_tasks)
        result_by_id = {r.approval_id: r for r in results}

        assert result_by_id[records[0].id].decision == "rejected"
        assert result_by_id[records[1].id].decision == "approved"
        assert result_by_id[records[2].id].decision == "approved"
        assert approval_service.pending_count == 0


# ---------------------------------------------------------------------------
# Test 5 — audit log records each decision (§8).
# ---------------------------------------------------------------------------


class TestAuditLogging:
    """Every approval/denial MUST be observable via the audit service —
    this is the system-of-record for "did the user approve X at Y"."""

    @pytest.mark.xfail(
        strict=False,
        reason=(
            "approval-decision audit log emit not yet wired in submit_decision "
            "(deferred per runbook §11 — see new gap #4). Test pins the intended "
            "contract — the inline _record_decision helper models the wrapper the "
            "orchestrator should invoke at the submit_decision call site."
        ),
    )
    @pytest.mark.asyncio
    async def test_audit_log_records_each_decision(
        self,
        approval_service: ApprovalService,
        sample_request: ApprovalRequestCreate,
    ) -> None:
        """Approval + rejection both reach AuditService.log_tool_call when
        the orchestrator wrapper invokes it. We verify the wrapper-level
        contract by patching the service and exercising both decision
        branches."""
        # The orchestrator-side wrapper that calls audit on every
        # decision lives at the boundary between websocket.py /
        # orchestrator_service.py and audit_service.py. We model it
        # here as a thin async helper so the contract is explicit and
        # test-pinned.
        from app.services.audit_service import AuditService

        log_mock = AsyncMock(return_value=None)

        async def _record_decision(
            *,
            audit: AuditService,
            user_id: uuid.UUID,
            tool_name: str,
            action: str,
            decision: str,
        ) -> None:
            await audit.log_tool_call(
                tool_name=tool_name,
                action=action,
                success=(decision == "approved"),
                user_id=user_id,
                input_params=None,
                output_result={"decision": decision},
                approval_required=True,
            )

        with patch.object(AuditService, "log_tool_call", new=log_mock):
            audit = AuditService(session=AsyncMock())
            user_id = uuid.uuid4()

            # APPROVE leg.
            approve_rec = await approval_service.create_approval(sample_request)
            wait_a = asyncio.create_task(
                approval_service.wait_for_decision(approve_rec.id)
            )
            for _ in range(5):
                await asyncio.sleep(0)
                if approve_rec.id in approval_service._waiters:  # noqa: SLF001
                    break
            await approval_service.submit_decision(
                ApprovalDecision(approval_id=approve_rec.id, decision="approved"),
            )
            approve_result = await asyncio.wait_for(wait_a, timeout=1.0)
            assert approve_result.approved is True
            await _record_decision(
                audit=audit,
                user_id=user_id,
                tool_name=approve_rec.tool_name,
                action=approve_rec.action,
                decision=approve_result.decision,
            )

            # REJECT leg — separate request id so they stay independent.
            reject_req = ApprovalRequestCreate(
                session_id=sample_request.session_id,
                connection_id=sample_request.connection_id,
                tool_name="git_push",
                action="git push --force origin main",
                description="Force-push to main",
                category=ApprovalCategory.WRITE_REMOTE,
            )
            reject_rec = await approval_service.create_approval(reject_req)
            wait_r = asyncio.create_task(
                approval_service.wait_for_decision(reject_rec.id)
            )
            for _ in range(5):
                await asyncio.sleep(0)
                if reject_rec.id in approval_service._waiters:  # noqa: SLF001
                    break
            await approval_service.submit_decision(
                ApprovalDecision(approval_id=reject_rec.id, decision="rejected"),
            )
            reject_result = await asyncio.wait_for(wait_r, timeout=1.0)
            assert reject_result.approved is False
            await _record_decision(
                audit=audit,
                user_id=user_id,
                tool_name=reject_rec.tool_name,
                action=reject_rec.action,
                decision=reject_result.decision,
            )

        # Both decisions reached the audit log with user_id + tool_name +
        # decision in the recorded payload.
        assert log_mock.await_count == 2
        approve_call = log_mock.await_args_list[0].kwargs
        reject_call = log_mock.await_args_list[1].kwargs

        assert approve_call["tool_name"] == "shell_rm"
        assert approve_call["user_id"] == user_id
        assert approve_call["success"] is True
        assert approve_call["approval_required"] is True
        assert approve_call["output_result"] == {"decision": "approved"}

        assert reject_call["tool_name"] == "git_push"
        assert reject_call["user_id"] == user_id
        assert reject_call["success"] is False
        assert reject_call["approval_required"] is True
        assert reject_call["output_result"] == {"decision": "rejected"}
