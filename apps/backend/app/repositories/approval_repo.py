"""Approval request repository — async database access layer."""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.approval_request import ApprovalRequest

logger: structlog.stdlib.BoundLogger = structlog.get_logger()


class ApprovalRepository:
    """DB access layer for approval_requests table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        id: uuid.UUID,
        session_id: str,
        tool_name: str,
        action: str,
        description: str,
        category: str,
        timeout_seconds: int = 300,
        timeout_at: datetime | None = None,
        connection_id: str | None = None,
        params: dict[str, object] | None = None,
    ) -> ApprovalRequest:
        """Create a new approval request record."""
        record = ApprovalRequest(
            id=id,
            session_id=session_id,
            connection_id=connection_id,
            tool_name=tool_name,
            action=action,
            description=description,
            params=params,
            category=category,
            status="pending",
            timeout_seconds=timeout_seconds,
            timeout_at=timeout_at,
        )
        self._session.add(record)
        await self._session.flush()
        await logger.adebug("approval_request_persisted", approval_id=str(id))
        return record

    async def update_status(
        self,
        approval_id: uuid.UUID,
        status: str,
        *,
        responded_at: datetime | None = None,
    ) -> None:
        """Update the status of an approval request."""
        values: dict[str, object] = {"status": status}
        if responded_at is not None:
            values["responded_at"] = responded_at
        stmt = (
            update(ApprovalRequest)
            .where(ApprovalRequest.id == approval_id)
            .values(**values)
        )
        await self._session.execute(stmt)

    async def get_pending(self, session_id: str) -> ApprovalRequest | None:
        """Get the pending approval for a session."""
        query = (
            select(ApprovalRequest)
            .where(
                ApprovalRequest.session_id == session_id,
                ApprovalRequest.status == "pending",
            )
            .order_by(ApprovalRequest.created_at.desc())
            .limit(1)
        )
        result = await self._session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_id(self, approval_id: uuid.UUID) -> ApprovalRequest | None:
        """Get approval request by ID."""
        query = select(ApprovalRequest).where(ApprovalRequest.id == approval_id)
        result = await self._session.execute(query)
        return result.scalar_one_or_none()

    async def list_history(self, *, limit: int = 50) -> Sequence[ApprovalRequest]:
        """List completed approval requests for audit, newest first."""
        query = (
            select(ApprovalRequest)
            .where(ApprovalRequest.status != "pending")
            .order_by(ApprovalRequest.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(query)
        return result.scalars().all()
