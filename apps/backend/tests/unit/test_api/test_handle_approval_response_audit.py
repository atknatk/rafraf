"""Unit tests for the approval-response audit-log wire-in (T3.2 #4).

Resolves runbook ``docs/runbooks/permission-flow.md`` §11 wiring gap #4
— ``AuditService.log_tool_call(approval_required=True, ...)`` MUST be
invoked at the ``submit_decision`` call site so each approval / denial
lands in ``audit_log`` regardless of whether the underlying tool ever
runs (rejected decisions never produce a tool row otherwise).

Tests exercise ``app.api.routes.websocket._handle_approval_response``
directly with the in-memory ``ApprovalService`` patched to a fresh
instance so each case starts from an empty pending map.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from app.api.routes import websocket as websocket_module
from app.schemas.approval import (
    ApprovalCategory,
    ApprovalRequestCreate,
)
from app.services.approval_service import ApprovalService


@pytest_asyncio.fixture
async def fresh_approval_service() -> AsyncIterator[ApprovalService]:
    """Yield a fresh ApprovalService with DB persistence stubbed out."""

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
            "app.core.database.async_session_factory",
            side_effect=lambda: _NoOpSession(),
        ),
        patch(
            "app.repositories.approval_repo.ApprovalRepository.create",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.repositories.approval_repo.ApprovalRepository.update_status",
            new=AsyncMock(return_value=None),
        ),
        patch.object(websocket_module, "get_approval_service", lambda: service),
        patch.object(
            websocket_module, "manager", MagicMock(send_json=AsyncMock(return_value=None))
        ),
    ):
        yield service


@pytest.fixture
def fake_audit_session_factory() -> MagicMock:
    """Replace ``async_session_factory`` in websocket.py with a stub session."""

    class _StubSession:
        def __init__(self) -> None:
            self.commit = AsyncMock(return_value=None)
            self.add = MagicMock()
            self.flush = AsyncMock(return_value=None)

        async def __aenter__(self) -> _StubSession:
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

    return MagicMock(side_effect=lambda: _StubSession())


def _make_approval_create(
    *,
    session_id: str,
    tool_name: str = "shell_rm",
    action: str = "rm -rf /tmp/scratch",
    category: ApprovalCategory = ApprovalCategory.DESTRUCTIVE,
) -> ApprovalRequestCreate:
    return ApprovalRequestCreate(
        session_id=session_id,
        connection_id=f"conn-{session_id}",
        tool_name=tool_name,
        action=action,
        description="Audit-wiring test approval",
        category=category,
    )


class TestApprovalResponseAuditEmit:
    """`_handle_approval_response` MUST call AuditService for each decision."""

    @pytest.mark.asyncio
    async def test_approve_decision_emits_audit_log(
        self,
        fresh_approval_service: ApprovalService,
        fake_audit_session_factory: MagicMock,
    ) -> None:
        """A successful 'approved' decision lands in audit_log with
        approval_required=True and success=True."""
        approval_create = _make_approval_create(session_id="sess-approve")
        record = await fresh_approval_service.create_approval(approval_create)

        # Spin up the awaiter so submit_decision() has a live waiter.
        wait_task = asyncio.create_task(fresh_approval_service.wait_for_decision(record.id))
        for _ in range(20):
            await asyncio.sleep(0)
            if record.id in fresh_approval_service._waiters:  # noqa: SLF001
                break

        log_mock = AsyncMock(return_value=None)
        user_uuid = uuid.uuid4()

        with (
            patch.object(websocket_module, "async_session_factory", fake_audit_session_factory),
            patch(
                "app.services.audit_service.AuditService.log_tool_call",
                new=log_mock,
            ),
        ):
            await websocket_module._handle_approval_response(
                {
                    "id": "msg-approve",
                    "type": "approval_response",
                    "content": {
                        "approval_id": record.id,
                        "decision": "approved",
                        "note": "ok",
                    },
                },
                connection_id="conn-approve",
                session_id="sess-approve",
                user_id=str(user_uuid),
            )

        await asyncio.wait_for(wait_task, timeout=1.0)

        assert log_mock.await_count == 1
        kwargs = log_mock.await_args.kwargs
        assert kwargs["tool_name"] == "shell_rm"
        assert kwargs["action"] == "rm -rf /tmp/scratch"
        assert kwargs["success"] is True
        assert kwargs["approval_required"] is True
        assert kwargs["user_id"] == user_uuid
        assert kwargs["session_id"] == "sess-approve"
        assert kwargs["output_result"] == {"decision": "approved"}

    @pytest.mark.asyncio
    async def test_reject_decision_emits_audit_log(
        self,
        fresh_approval_service: ApprovalService,
        fake_audit_session_factory: MagicMock,
    ) -> None:
        """Rejection MUST also reach the audit log — this is the row no
        other code path ever creates (the tool never runs)."""
        approval_create = _make_approval_create(
            session_id="sess-reject",
            tool_name="git_push",
            action="git push --force origin main",
            category=ApprovalCategory.WRITE_REMOTE,
        )
        record = await fresh_approval_service.create_approval(approval_create)

        wait_task = asyncio.create_task(fresh_approval_service.wait_for_decision(record.id))
        for _ in range(20):
            await asyncio.sleep(0)
            if record.id in fresh_approval_service._waiters:  # noqa: SLF001
                break

        log_mock = AsyncMock(return_value=None)
        user_uuid = uuid.uuid4()

        with (
            patch.object(websocket_module, "async_session_factory", fake_audit_session_factory),
            patch(
                "app.services.audit_service.AuditService.log_tool_call",
                new=log_mock,
            ),
        ):
            await websocket_module._handle_approval_response(
                {
                    "id": "msg-reject",
                    "type": "approval_response",
                    "content": {
                        "approval_id": record.id,
                        "decision": "rejected",
                    },
                },
                connection_id="conn-reject",
                session_id="sess-reject",
                user_id=str(user_uuid),
            )

        await asyncio.wait_for(wait_task, timeout=1.0)

        assert log_mock.await_count == 1
        kwargs = log_mock.await_args.kwargs
        assert kwargs["success"] is False
        assert kwargs["approval_required"] is True
        assert kwargs["output_result"] == {"decision": "rejected"}
        assert kwargs["tool_name"] == "git_push"

    @pytest.mark.asyncio
    async def test_no_pending_record_skips_audit_emit(
        self,
        fresh_approval_service: ApprovalService,  # noqa: ARG002 — fixture installs the patches
        fake_audit_session_factory: MagicMock,
    ) -> None:
        """When the approval id is unknown (already consumed or stale)
        the helper MUST NOT pollute the audit log with a phantom row."""
        log_mock = AsyncMock(return_value=None)

        with (
            patch.object(websocket_module, "async_session_factory", fake_audit_session_factory),
            patch(
                "app.services.audit_service.AuditService.log_tool_call",
                new=log_mock,
            ),
        ):
            await websocket_module._handle_approval_response(
                {
                    "id": "msg-stale",
                    "type": "approval_response",
                    "content": {
                        "approval_id": "stale-id-no-pending",
                        "decision": "approved",
                    },
                },
                connection_id="conn-stale",
                session_id="sess-stale",
                user_id=str(uuid.uuid4()),
            )

        assert log_mock.await_count == 0

    @pytest.mark.asyncio
    async def test_audit_emit_failure_does_not_break_handler(
        self,
        fresh_approval_service: ApprovalService,
    ) -> None:
        """If the audit DB write blows up the WebSocket flow MUST still
        complete — the rest of the runtime (especially submit_decision)
        cannot block on audit persistence."""
        approval_create = _make_approval_create(session_id="sess-audit-fail")
        record = await fresh_approval_service.create_approval(approval_create)

        wait_task = asyncio.create_task(fresh_approval_service.wait_for_decision(record.id))
        for _ in range(20):
            await asyncio.sleep(0)
            if record.id in fresh_approval_service._waiters:  # noqa: SLF001
                break

        # Make async_session_factory raise on entry so the helper trips.
        boom_factory = MagicMock(side_effect=RuntimeError("audit db down"))

        with patch.object(websocket_module, "async_session_factory", boom_factory):
            # The handler MUST NOT raise.
            await websocket_module._handle_approval_response(
                {
                    "id": "msg-audit-fail",
                    "type": "approval_response",
                    "content": {
                        "approval_id": record.id,
                        "decision": "approved",
                    },
                },
                connection_id="conn-audit-fail",
                session_id="sess-audit-fail",
                user_id=str(uuid.uuid4()),
            )

        result = await asyncio.wait_for(wait_task, timeout=1.0)
        # Decision still propagated despite audit failure.
        assert result.approved is True

    @pytest.mark.asyncio
    async def test_non_uuid_user_id_falls_back_to_none(
        self,
        fresh_approval_service: ApprovalService,
        fake_audit_session_factory: MagicMock,
    ) -> None:
        """Test/dev tokens may carry non-UUID subjects (e.g. ``test-user``).
        The helper MUST still record the row with ``user_id=None`` rather
        than crash on UUID parse."""
        approval_create = _make_approval_create(session_id="sess-non-uuid")
        record = await fresh_approval_service.create_approval(approval_create)

        wait_task = asyncio.create_task(fresh_approval_service.wait_for_decision(record.id))
        for _ in range(20):
            await asyncio.sleep(0)
            if record.id in fresh_approval_service._waiters:  # noqa: SLF001
                break

        log_mock = AsyncMock(return_value=None)

        with (
            patch.object(websocket_module, "async_session_factory", fake_audit_session_factory),
            patch(
                "app.services.audit_service.AuditService.log_tool_call",
                new=log_mock,
            ),
        ):
            await websocket_module._handle_approval_response(
                {
                    "id": "msg-non-uuid",
                    "type": "approval_response",
                    "content": {
                        "approval_id": record.id,
                        "decision": "approved",
                    },
                },
                connection_id="conn-non-uuid",
                session_id="sess-non-uuid",
                user_id="not-a-uuid-at-all",
            )

        await asyncio.wait_for(wait_task, timeout=1.0)

        assert log_mock.await_count == 1
        kwargs = log_mock.await_args.kwargs
        assert kwargs["user_id"] is None
        # session_id still recorded so the row is searchable.
        assert kwargs["session_id"] == "sess-non-uuid"
        # cast guards against MagicMock attribute access in mypy strict.
        _ = cast(str, kwargs["session_id"])
