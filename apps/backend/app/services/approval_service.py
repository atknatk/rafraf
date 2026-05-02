"""Approval service - interactive question flow for high-risk operations."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import structlog

from app.schemas.approval import (
    APPROVAL_MATRIX,
    CATEGORY_TIMEOUTS,
    ApprovalCategory,
    ApprovalDecision,
    ApprovalRequestCreate,
    ApprovalRequestRecord,
    ApprovalResult,
    ApprovalStatus,
)
from app.schemas.messages import (
    MessageDirection,
    MessageType,
    QuestionOptionPayload,
    QuestionPayload,
)

logger: structlog.stdlib.BoundLogger = structlog.get_logger()


class ApprovalService:
    """Manages the approval lifecycle: create, wait, decide, expire.

    Holds pending approval requests in memory and coordinates with the
    WebSocket layer to send questions and receive responses.
    """

    def __init__(self) -> None:
        # In-memory store for pending approvals: approval_id -> record
        self._pending: dict[str, ApprovalRequestRecord] = {}
        # Futures waiting for user decisions: approval_id -> Future
        self._waiters: dict[str, asyncio.Future[ApprovalDecision]] = {}
        # History of completed approvals for audit
        self._history: list[ApprovalRequestRecord] = []

    def check_requires_approval(self, tool_name: str) -> bool:
        """Check if a tool requires user approval.

        Args:
            tool_name: Name of the tool to check.

        Returns:
            True if approval is required for this tool.
        """
        return tool_name in APPROVAL_MATRIX

    def get_approval_category(self, tool_name: str) -> ApprovalCategory | None:
        """Get the approval category for a tool.

        Args:
            tool_name: Name of the tool.

        Returns:
            ApprovalCategory if tool requires approval, None otherwise.
        """
        return APPROVAL_MATRIX.get(tool_name)

    async def create_approval(
        self,
        request: ApprovalRequestCreate,
    ) -> ApprovalRequestRecord:
        """Create a new approval request.

        V1.4: when ``request.timeout_seconds`` is supplied AND no
        ``CATEGORY_TIMEOUTS`` override exists for this category, the
        caller-provided value wins. The bridge ``permission_request``
        envelope passes ``timeout_ms`` (default 30 s) which the runner
        rounds up to ``timeout_seconds``; honouring it keeps the four
        layers (iOS RFApprovalSheet countdown, backend
        ``ApprovalService`` timer, bridge UDS broker, claude CLI hook
        timeout) aligned. See design doc §4.3 timeout cascade table.

        Args:
            request: Approval request creation data.

        Returns:
            The created ApprovalRequestRecord.
        """
        category = request.category
        timeout = CATEGORY_TIMEOUTS.get(category, request.timeout_seconds)
        now = datetime.now(tz=UTC)

        record = ApprovalRequestRecord(
            id=str(uuid4()),
            session_id=request.session_id,
            connection_id=request.connection_id,
            tool_name=request.tool_name,
            action=request.action,
            description=request.description,
            params=request.params,
            category=category,
            status=ApprovalStatus.PENDING,
            timeout_seconds=timeout,
            timeout_at=now + timedelta(seconds=timeout),
            created_at=now,
            request_id=request.request_id,
            bridge_host_id=request.bridge_host_id,
            rpc_id=request.rpc_id,
            bridge_timeout_seconds=(
                request.timeout_seconds if request.request_id is not None else None
            ),
        )

        self._pending[record.id] = record

        # Persist to DB (best-effort)
        try:
            from uuid import UUID as _UUID

            from app.core.database import async_session_factory
            from app.repositories.approval_repo import ApprovalRepository

            async with async_session_factory() as db:
                repo = ApprovalRepository(db)
                await repo.create(
                    id=_UUID(record.id),
                    session_id=record.session_id,
                    connection_id=record.connection_id,
                    tool_name=record.tool_name,
                    action=record.action,
                    description=record.description,
                    category=category.value,
                    timeout_seconds=timeout,
                    timeout_at=record.timeout_at,
                    params=record.params,
                    request_id=record.request_id,
                    bridge_host_id=record.bridge_host_id,
                    rpc_id=record.rpc_id,
                    bridge_timeout_seconds=record.bridge_timeout_seconds,
                )
                await db.commit()
        except Exception:
            await logger.awarning("approval_db_persist_failed", approval_id=record.id)

        await logger.ainfo(
            "approval_created",
            approval_id=record.id,
            tool_name=record.tool_name,
            action=record.action,
            category=category.value,
            timeout_seconds=timeout,
        )

        return record

    async def wait_for_decision(
        self,
        approval_id: str,
        *,
        timeout_override: int | None = None,
    ) -> ApprovalResult:
        """Wait for a user decision on an approval request.

        Blocks until the user responds or the timeout expires.

        V1.4: ``timeout_override`` lets the bridge ``permission_request``
        awaiter use the bridge-suggested deadline (default 30 s) rather
        than the per-category default (180–300 s). When provided AND
        positive AND less than the record's ``timeout_seconds``, the
        override wins; otherwise the record's timer applies. We never
        let the override extend beyond the record's deadline because
        that would let a malicious bridge envelope pin a request open
        forever.

        Args:
            approval_id: ID of the approval request.
            timeout_override: Optional shorter deadline (seconds).

        Returns:
            ApprovalResult with the decision.
        """
        record = self._pending.get(approval_id)
        if record is None:
            return ApprovalResult(
                approved=False,
                approval_id=approval_id,
                decision="not_found",
                note="Approval request not found",
            )

        effective_timeout = float(record.timeout_seconds)
        if timeout_override is not None and timeout_override > 0:
            effective_timeout = min(effective_timeout, float(timeout_override))

        # Create a future for this approval
        loop = asyncio.get_running_loop()
        future: asyncio.Future[ApprovalDecision] = loop.create_future()
        self._waiters[approval_id] = future

        try:
            decision = await asyncio.wait_for(
                future,
                timeout=effective_timeout,
            )

            # Process the decision
            return await self._process_decision(approval_id, decision)

        except TimeoutError:
            # Timeout - mark as expired
            return await self._expire_approval(approval_id)

        finally:
            self._waiters.pop(approval_id, None)

    async def submit_decision(self, decision: ApprovalDecision) -> bool:
        """Submit a user's decision for a pending approval.

        Called by the WebSocket handler when an approval_response arrives.

        Args:
            decision: The user's decision.

        Returns:
            True if the decision was submitted, False if no pending request.
        """
        future = self._waiters.get(decision.approval_id)
        if future is None or future.done():
            await logger.awarning(
                "approval_decision_no_waiter",
                approval_id=decision.approval_id,
            )
            return False

        future.set_result(decision)

        await logger.ainfo(
            "approval_decision_submitted",
            approval_id=decision.approval_id,
            decision=decision.decision,
        )

        return True

    async def _process_decision(
        self,
        approval_id: str,
        decision: ApprovalDecision,
    ) -> ApprovalResult:
        """Process a user decision and update the approval record.

        Args:
            approval_id: ID of the approval request.
            decision: The user's decision.

        Returns:
            ApprovalResult based on the decision.
        """
        record = self._pending.pop(approval_id, None)
        if record is None:
            return ApprovalResult(
                approved=False,
                approval_id=approval_id,
                decision="not_found",
            )

        now = datetime.now(tz=UTC)
        new_status = (
            ApprovalStatus.APPROVED if decision.decision == "approved" else ApprovalStatus.REJECTED
        )

        updated = ApprovalRequestRecord(
            id=record.id,
            session_id=record.session_id,
            connection_id=record.connection_id,
            tool_name=record.tool_name,
            action=record.action,
            description=record.description,
            params=record.params,
            category=record.category,
            status=new_status,
            timeout_seconds=record.timeout_seconds,
            timeout_at=record.timeout_at,
            created_at=record.created_at,
            responded_at=now,
            request_id=record.request_id,
            bridge_host_id=record.bridge_host_id,
            rpc_id=record.rpc_id,
            bridge_timeout_seconds=record.bridge_timeout_seconds,
        )

        self._history.append(updated)

        # Persist status to DB (best-effort)
        try:
            from uuid import UUID as _UUID

            from app.core.database import async_session_factory
            from app.repositories.approval_repo import ApprovalRepository

            async with async_session_factory() as db:
                repo = ApprovalRepository(db)
                await repo.update_status(
                    _UUID(approval_id),
                    new_status.value,
                    responded_at=now,
                )
                await db.commit()
        except Exception:
            await logger.awarning("approval_decision_db_failed", approval_id=approval_id)

        await logger.ainfo(
            "approval_processed",
            approval_id=approval_id,
            status=new_status.value,
            decision=decision.decision,
        )

        return ApprovalResult(
            approved=decision.decision == "approved",
            approval_id=approval_id,
            decision=decision.decision,
            note=decision.note,
        )

    async def _expire_approval(self, approval_id: str) -> ApprovalResult:
        """Mark an approval as expired due to timeout.

        Args:
            approval_id: ID of the approval request.

        Returns:
            ApprovalResult with expired status.
        """
        record = self._pending.pop(approval_id, None)
        if record is not None:
            expired = ApprovalRequestRecord(
                id=record.id,
                session_id=record.session_id,
                connection_id=record.connection_id,
                tool_name=record.tool_name,
                action=record.action,
                description=record.description,
                params=record.params,
                category=record.category,
                status=ApprovalStatus.EXPIRED,
                timeout_seconds=record.timeout_seconds,
                timeout_at=record.timeout_at,
                created_at=record.created_at,
                request_id=record.request_id,
                bridge_host_id=record.bridge_host_id,
                rpc_id=record.rpc_id,
                bridge_timeout_seconds=record.bridge_timeout_seconds,
            )
            self._history.append(expired)

            # Persist expired status to DB (best-effort)
            try:
                from uuid import UUID as _UUID

                from app.core.database import async_session_factory
                from app.repositories.approval_repo import ApprovalRepository

                async with async_session_factory() as db:
                    repo = ApprovalRepository(db)
                    await repo.update_status(_UUID(approval_id), "expired")
                    await db.commit()
            except Exception:
                await logger.awarning("approval_expire_db_failed", approval_id=approval_id)

        await logger.awarning(
            "approval_expired",
            approval_id=approval_id,
        )

        return ApprovalResult(
            approved=False,
            approval_id=approval_id,
            decision="expired",
            note="Approval request timed out",
        )

    def get_pending_approval(self, approval_id: str) -> ApprovalRequestRecord | None:
        """Get a pending approval by ID.

        Args:
            approval_id: Approval request ID.

        Returns:
            ApprovalRequestRecord if found, None otherwise.
        """
        return self._pending.get(approval_id)

    def get_session_pending(self, session_id: str) -> ApprovalRequestRecord | None:
        """Get the pending approval for a session (max 1 at a time).

        Args:
            session_id: WebSocket session ID.

        Returns:
            The pending approval record if one exists, None otherwise.
        """
        for record in self._pending.values():
            if record.session_id == session_id:
                return record
        return None

    def get_history(self, *, limit: int = 50) -> list[ApprovalRequestRecord]:
        """Return recent approval history for audit.

        Args:
            limit: Maximum number of records to return.

        Returns:
            List of completed approval records, newest first.
        """
        return list(reversed(self._history[-limit:]))

    @property
    def pending_count(self) -> int:
        """Return the number of pending approvals."""
        return len(self._pending)

    def build_question_message(
        self,
        record: ApprovalRequestRecord,
        session_id: str,
    ) -> dict[str, object]:
        """Build a WebSocket 'question' message for an approval request.

        Args:
            record: The approval request record.
            session_id: Current session ID.

        Returns:
            Dict formatted as a WebSocket question message.
        """
        question_payload = QuestionPayload(
            approval_id=record.id,
            question=record.description,
            context=f"Tool: {record.tool_name}, Action: {record.action}",
            options=[
                QuestionOptionPayload(id="approve", label="Onayla", style="primary"),
                QuestionOptionPayload(id="reject", label="Reddet", style="danger"),
            ],
            timeout_seconds=record.timeout_seconds,
            category=record.category.value,
        )

        now = datetime.now(tz=UTC).isoformat()
        return {
            "id": str(uuid4()),
            "type": MessageType.QUESTION.value,
            "content": question_payload.model_dump(),
            "metadata": {
                "timestamp": now,
                "session_id": session_id,
                "direction": MessageDirection.SERVER_TO_CLIENT.value,
            },
        }


# Module-level singleton
_approval_service: ApprovalService | None = None


def get_approval_service() -> ApprovalService:
    """Get or create the global ApprovalService singleton.

    Returns:
        Global ApprovalService instance.
    """
    global _approval_service  # noqa: PLW0603
    if _approval_service is None:
        _approval_service = ApprovalService()
    return _approval_service
