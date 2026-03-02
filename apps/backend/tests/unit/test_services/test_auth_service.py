"""Unit tests for AuthService."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import UnauthorizedError
from app.core.security import hash_password
from app.services.auth_service import AuthService


def _make_mock_user(
    user_id: uuid.UUID | None = None,
    email: str = "test@example.com",
    password: str = "testpass123",
    is_active: bool = True,
) -> MagicMock:
    """Create a mock User object."""
    user = MagicMock()
    user.id = user_id or uuid.uuid4()
    user.email = email
    user.hashed_password = hash_password(password)
    user.is_active = is_active
    return user


class TestAuthenticate:
    """Tests for AuthService.authenticate."""

    async def test_authenticate_valid_credentials(self) -> None:
        """authenticate should return TokenResponse for valid credentials."""
        mock_session = AsyncMock()
        service = AuthService(mock_session)
        mock_user = _make_mock_user()

        with patch.object(service._repo, "get_by_email", return_value=mock_user):
            result = await service.authenticate("test@example.com", "testpass123")

        assert result.access_token
        assert result.refresh_token
        assert result.token_type == "bearer"
        assert result.expires_in == 900  # 15 min * 60

    async def test_authenticate_wrong_password(self) -> None:
        """authenticate should raise UnauthorizedError for wrong password."""
        mock_session = AsyncMock()
        service = AuthService(mock_session)
        mock_user = _make_mock_user()

        with (
            patch.object(service._repo, "get_by_email", return_value=mock_user),
            pytest.raises(UnauthorizedError, match="Invalid email or password"),
        ):
            await service.authenticate("test@example.com", "wrongpassword")

    async def test_authenticate_user_not_found(self) -> None:
        """authenticate should raise UnauthorizedError when user not found."""
        mock_session = AsyncMock()
        service = AuthService(mock_session)

        with (
            patch.object(service._repo, "get_by_email", return_value=None),
            pytest.raises(UnauthorizedError, match="Invalid email or password"),
        ):
            await service.authenticate("nobody@example.com", "testpass123")

    async def test_authenticate_inactive_user(self) -> None:
        """authenticate should raise UnauthorizedError for inactive user."""
        mock_session = AsyncMock()
        service = AuthService(mock_session)
        mock_user = _make_mock_user(is_active=False)

        with (
            patch.object(service._repo, "get_by_email", return_value=mock_user),
            pytest.raises(UnauthorizedError, match="inactive"),
        ):
            await service.authenticate("test@example.com", "testpass123")


class TestRefreshTokens:
    """Tests for AuthService.refresh_tokens."""

    async def test_refresh_tokens_valid(self) -> None:
        """refresh_tokens should return new tokens for valid refresh token."""
        from app.core.security import create_refresh_token

        mock_session = AsyncMock()
        service = AuthService(mock_session)
        user_id = uuid.uuid4()
        mock_user = _make_mock_user(user_id=user_id)
        refresh_token = create_refresh_token(subject=str(user_id))

        with patch.object(service._repo, "get_by_id", return_value=mock_user):
            result = await service.refresh_tokens(refresh_token)

        assert result.access_token
        assert result.refresh_token
        assert result.token_type == "bearer"

    async def test_refresh_tokens_invalid_token(self) -> None:
        """refresh_tokens should raise UnauthorizedError for invalid token."""
        mock_session = AsyncMock()
        service = AuthService(mock_session)

        with pytest.raises(UnauthorizedError, match="Invalid or expired refresh token"):
            await service.refresh_tokens("invalid.token.value")

    async def test_refresh_tokens_user_not_found(self) -> None:
        """refresh_tokens should raise UnauthorizedError when user not found."""
        from app.core.security import create_refresh_token

        mock_session = AsyncMock()
        service = AuthService(mock_session)
        user_id = uuid.uuid4()
        refresh_token = create_refresh_token(subject=str(user_id))

        with (
            patch.object(service._repo, "get_by_id", return_value=None),
            pytest.raises(UnauthorizedError, match="User not found or inactive"),
        ):
            await service.refresh_tokens(refresh_token)

    async def test_refresh_tokens_inactive_user(self) -> None:
        """refresh_tokens should raise UnauthorizedError for inactive user."""
        from app.core.security import create_refresh_token

        mock_session = AsyncMock()
        service = AuthService(mock_session)
        user_id = uuid.uuid4()
        mock_user = _make_mock_user(user_id=user_id, is_active=False)
        refresh_token = create_refresh_token(subject=str(user_id))

        with (
            patch.object(service._repo, "get_by_id", return_value=mock_user),
            pytest.raises(UnauthorizedError, match="User not found or inactive"),
        ):
            await service.refresh_tokens(refresh_token)

    async def test_refresh_tokens_access_token_rejected(self) -> None:
        """refresh_tokens should reject an access token (wrong type)."""
        from app.core.security import create_access_token

        mock_session = AsyncMock()
        service = AuthService(mock_session)
        access_token = create_access_token(subject=str(uuid.uuid4()))

        with pytest.raises(UnauthorizedError, match="Invalid or expired refresh token"):
            await service.refresh_tokens(access_token)
