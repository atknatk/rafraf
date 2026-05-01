"""Session service — WebSocket session lifecycle management."""

import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.session_repo import SessionRepository

logger: structlog.stdlib.BoundLogger = structlog.get_logger()


class SessionService:
    """Manages session creation/closure tied to WebSocket lifecycle."""

    def __init__(self, session: AsyncSession) -> None:
        self._repo = SessionRepository(session)

    async def create_session(self, user_id: uuid.UUID) -> uuid.UUID:
        """Create a new session and return its ID."""
        record = await self._repo.create(user_id=user_id)
        return record.id

    async def end_session(self, session_id: uuid.UUID) -> None:
        """Mark a session as ended."""
        await self._repo.end_session(session_id)

    async def update_stats(
        self,
        session_id: uuid.UUID,
        *,
        message_count_increment: int = 0,
        tokens_input: int = 0,
        tokens_output: int = 0,
    ) -> None:
        """Increment session statistics after a message exchange.

        Cost tracking removed alongside cost service deletion (T0.7+T0.8).
        """
        await self._repo.update_stats(
            session_id,
            message_count_increment=message_count_increment,
            tokens_input=tokens_input,
            tokens_output=tokens_output,
        )
