"""Shared API dependencies for dependency injection."""

import uuid
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import get_session
from app.core.exceptions import UnauthorizedError
from app.core.security import SecurityError, verify_access_token
from app.models.user import User
from app.repositories.user_repository import UserRepository


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Provide a database session dependency."""
    async for session in get_session():
        yield session


def get_current_settings() -> Settings:
    """Provide application settings dependency."""
    return get_settings()


async def get_current_user(
    session: Annotated[AsyncSession, Depends(get_db)],
    authorization: Annotated[str | None, Header(description="Bearer <access_token>")] = None,
) -> User:
    """Extract and validate the current user from the Authorization header.

    Expects: Authorization: Bearer <access_token>

    Raises:
        UnauthorizedError: If the token is missing, invalid, or user not found.
    """
    if authorization is None:
        raise UnauthorizedError(message="Authorization header is required")

    if not authorization.startswith("Bearer "):
        raise UnauthorizedError(message="Invalid authorization header format")

    token = authorization[len("Bearer ") :]

    try:
        user_id = verify_access_token(token)
    except SecurityError as exc:
        raise UnauthorizedError(message="Invalid or expired access token") from exc

    repo = UserRepository(session)
    user = await repo.get_by_id(uuid.UUID(user_id))
    if user is None or not user.is_active:
        raise UnauthorizedError(message="User not found or inactive")

    return user


__all__ = ["Depends", "get_current_settings", "get_current_user", "get_db"]
