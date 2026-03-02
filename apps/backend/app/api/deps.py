"""Shared API dependencies for dependency injection."""

from collections.abc import AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import get_session


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Provide a database session dependency."""
    async for session in get_session():
        yield session


def get_current_settings() -> Settings:
    """Provide application settings dependency."""
    return get_settings()


__all__ = ["Depends", "get_current_settings", "get_db"]
