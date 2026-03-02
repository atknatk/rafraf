"""Authentication service - business logic for JWT auth."""

import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import UnauthorizedError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
    verify_refresh_token,
)
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.auth import TokenResponse

logger: structlog.stdlib.BoundLogger = structlog.get_logger()


class AuthService:
    """Service for authentication operations."""

    def __init__(self, session: AsyncSession) -> None:
        self._repo = UserRepository(session)
        self._session = session

    async def authenticate(self, email: str, password: str) -> TokenResponse:
        """Authenticate a user and return JWT tokens.

        Raises:
            UnauthorizedError: If credentials are invalid.
        """
        user = await self._repo.get_by_email(email)
        if user is None or not verify_password(password, user.hashed_password):
            await logger.awarning("auth_failed", email=email)
            raise UnauthorizedError(message="Invalid email or password")

        if not user.is_active:
            await logger.awarning("auth_inactive_user", email=email)
            raise UnauthorizedError(message="User account is inactive")

        return self._create_token_response(str(user.id))

    async def refresh_tokens(self, refresh_token_str: str) -> TokenResponse:
        """Refresh JWT tokens using a refresh token.

        Raises:
            UnauthorizedError: If the refresh token is invalid.
        """
        from app.core.security import SecurityError

        try:
            user_id = verify_refresh_token(refresh_token_str)
        except SecurityError as exc:
            raise UnauthorizedError(message="Invalid or expired refresh token") from exc

        # Verify user still exists and is active
        user = await self._repo.get_by_id(uuid.UUID(user_id))
        if user is None or not user.is_active:
            raise UnauthorizedError(message="User not found or inactive")

        await logger.ainfo("token_refreshed", user_id=user_id)
        return self._create_token_response(user_id)

    async def register_user(self, email: str, password: str) -> User:
        """Register a new user with hashed password.

        This is a convenience method for seeding/testing.
        """
        hashed = hash_password(password)
        user = await self._repo.create(email=email, hashed_password=hashed)
        await logger.ainfo("user_registered", user_id=str(user.id), email=email)
        return user

    def _create_token_response(self, user_id: str) -> TokenResponse:
        """Create a token response with access and refresh tokens."""
        settings = get_settings()
        access_token = create_access_token(subject=user_id)
        refresh_token = create_refresh_token(subject=user_id)
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=settings.jwt_access_token_expire_minutes * 60,
        )
