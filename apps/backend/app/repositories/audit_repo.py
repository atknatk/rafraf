"""Audit log repository — async database access layer."""

import uuid
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog

logger: structlog.stdlib.BoundLogger = structlog.get_logger()


class AuditRepository:
    """DB access layer for audit_log table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        tool_name: str,
        action: str,
        success: bool,
        session_id: str | None = None,
        user_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        host_id: str | None = None,
        input_params: dict[str, object] | None = None,
        output_result: dict[str, object] | None = None,
        error_message: str | None = None,
        duration_ms: int | None = None,
        approval_required: bool = False,
        approved_at: datetime | None = None,
        model_used: str | None = None,
        tokens_used: dict[str, object] | None = None,
        cost_usd: Decimal | None = None,
    ) -> AuditLog:
        """Create an audit log entry."""
        record = AuditLog(
            tool_name=tool_name,
            action=action,
            success=success,
            session_id=session_id,
            user_id=user_id,
            project_id=project_id,
            host_id=host_id,
            input_params=input_params,
            output_result=output_result,
            error_message=error_message,
            duration_ms=duration_ms,
            approval_required=approval_required,
            approved_at=approved_at,
            model_used=model_used,
            tokens_used=tokens_used,
            cost_usd=cost_usd,
        )
        self._session.add(record)
        await self._session.flush()
        await logger.adebug("audit_log_created", tool_name=tool_name, action=action)
        return record

    async def list_by_session(
        self,
        session_id: str,
        *,
        limit: int = 100,
    ) -> Sequence[AuditLog]:
        """List audit log entries for a session."""
        query = (
            select(AuditLog)
            .where(AuditLog.session_id == session_id)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(query)
        return result.scalars().all()

    async def list_by_tool(
        self,
        tool_name: str,
        *,
        limit: int = 100,
    ) -> Sequence[AuditLog]:
        """List audit log entries by tool name."""
        query = (
            select(AuditLog)
            .where(AuditLog.tool_name == tool_name)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(query)
        return result.scalars().all()

    async def list_recent(self, *, limit: int = 50) -> Sequence[AuditLog]:
        """List most recent audit log entries."""
        query = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
        result = await self._session.execute(query)
        return result.scalars().all()
