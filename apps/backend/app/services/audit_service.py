"""Audit service — logs tool executions for compliance and analytics."""

import uuid
from datetime import datetime
from decimal import Decimal

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.audit_repo import AuditRepository

logger: structlog.stdlib.BoundLogger = structlog.get_logger()


class AuditService:
    """Writes audit log entries after tool executions."""

    def __init__(self, session: AsyncSession) -> None:
        self._repo = AuditRepository(session)

    async def log_tool_call(
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
    ) -> None:
        """Record a tool execution in the audit log.

        Failures are logged but never raised — audit must not break operations.
        """
        try:
            await self._repo.create(
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
        except Exception:
            await logger.aexception(
                "audit_log_write_failed",
                tool_name=tool_name,
                action=action,
            )
