"""Session repository — async database access layer."""

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session import Session

logger: structlog.stdlib.BoundLogger = structlog.get_logger()


class SessionRepository:
    """DB access layer for sessions table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, user_id: uuid.UUID) -> Session:
        """Create a new session record."""
        record = Session(user_id=user_id)
        self._session.add(record)
        await self._session.flush()
        await self._session.refresh(record)
        await logger.ainfo("session_created", session_id=str(record.id))
        return record

    async def end_session(self, session_id: uuid.UUID) -> None:
        """Mark a session as ended."""
        now = datetime.now(tz=UTC)
        stmt = update(Session).where(Session.id == session_id).values(ended_at=now, updated_at=now)
        await self._session.execute(stmt)
        await logger.ainfo("session_ended", session_id=str(session_id))

    async def get_by_id(self, session_id: uuid.UUID) -> Session | None:
        """Get a session by ID."""
        query = select(Session).where(Session.id == session_id)
        result = await self._session.execute(query)
        return result.scalar_one_or_none()

    async def get_active_by_user(self, user_id: uuid.UUID) -> list[Session]:
        """Get active (not ended) sessions for a user."""
        query = (
            select(Session)
            .where(Session.user_id == user_id, Session.ended_at.is_(None))
            .order_by(Session.started_at.desc())
        )
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def update_stats(
        self,
        session_id: uuid.UUID,
        *,
        message_count_increment: int = 0,
        tokens_input: int = 0,
        tokens_output: int = 0,
    ) -> None:
        """Increment session statistics (message count + token totals).

        Cost tracking removed alongside cost service deletion (T0.7+T0.8);
        the ``sessions.total_cost_usd`` column is left in the schema for
        backwards compatibility but is no longer written by the application.
        """
        record = await self.get_by_id(session_id)
        if record is None:
            return
        record.message_count += message_count_increment
        current_tokens = record.total_tokens_used or {"input": 0, "output": 0}
        input_val = current_tokens.get("input", 0)
        output_val = current_tokens.get("output", 0)
        current_tokens["input"] = (
            int(input_val) if isinstance(input_val, (int, float)) else 0
        ) + tokens_input
        current_tokens["output"] = (
            int(output_val) if isinstance(output_val, (int, float)) else 0
        ) + tokens_output
        record.total_tokens_used = current_tokens
        await self._session.flush()
