"""Integration tests for auth REST endpoints.

Uses FastAPI dependency override for DB session mocking.
"""

import uuid
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.security import create_refresh_token, hash_password
from app.main import app


def _make_mock_user(
    user_id: uuid.UUID | None = None,
    email: str = "test@example.com",
    password: str = "testpass123",
    is_active: bool = True,
) -> MagicMock:
    """Create a mock User object with hashed password."""
    user = MagicMock()
    user.id = user_id or uuid.uuid4()
    user.email = email
    user.hashed_password = hash_password(password)
    user.is_active = is_active
    return user


def _make_db_override(
    return_user: MagicMock | None = None,
) -> object:
    """Create a get_db dependency override."""
    mock_session = AsyncMock(spec=AsyncSession)
    # The result of execute() returns a sync Result-like object
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = return_user
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.flush = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()

    async def override() -> AsyncGenerator[AsyncSession, None]:
        yield mock_session  # type: ignore[misc]

    return override


@pytest.fixture(autouse=True)
def _clear_overrides() -> None:  # type: ignore[misc]
    """Clear FastAPI dependency overrides after each test."""
    yield  # type: ignore[misc]
    app.dependency_overrides.clear()


class TestLoginEndpoint:
    """Integration tests for POST /api/v1/auth/token."""

    def test_login_success(self) -> None:
        """Successful login should return 200 with tokens."""
        mock_user = _make_mock_user()
        app.dependency_overrides[get_db] = _make_db_override(mock_user)
        client = TestClient(app)

        response = client.post(
            "/api/v1/auth/token",
            json={"email": "test@example.com", "password": "testpass123"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        assert data["expires_in"] == 900

    def test_login_invalid_credentials(self) -> None:
        """Login with wrong password should return 401."""
        mock_user = _make_mock_user()
        app.dependency_overrides[get_db] = _make_db_override(mock_user)
        client = TestClient(app)

        response = client.post(
            "/api/v1/auth/token",
            json={"email": "test@example.com", "password": "wrongpassword"},
        )
        assert response.status_code == 401

    def test_login_user_not_found(self) -> None:
        """Login with non-existent email should return 401."""
        app.dependency_overrides[get_db] = _make_db_override(None)
        client = TestClient(app)

        response = client.post(
            "/api/v1/auth/token",
            json={"email": "nobody@example.com", "password": "testpass123"},
        )
        assert response.status_code == 401

    def test_login_invalid_email_format(self) -> None:
        """Login with invalid email format should return 422."""
        client = TestClient(app)
        response = client.post(
            "/api/v1/auth/token",
            json={"email": "not-an-email", "password": "testpass123"},
        )
        assert response.status_code == 422

    def test_login_missing_password(self) -> None:
        """Login without password should return 422."""
        client = TestClient(app)
        response = client.post(
            "/api/v1/auth/token",
            json={"email": "test@example.com"},
        )
        assert response.status_code == 422


class TestRefreshEndpoint:
    """Integration tests for POST /api/v1/auth/refresh."""

    def test_refresh_success(self) -> None:
        """Valid refresh token should return new tokens."""
        user_id = uuid.uuid4()
        mock_user = _make_mock_user(user_id=user_id)
        refresh_token = create_refresh_token(subject=str(user_id))
        app.dependency_overrides[get_db] = _make_db_override(mock_user)
        client = TestClient(app)

        response = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data

    def test_refresh_invalid_token(self) -> None:
        """Invalid refresh token should return 401."""
        client = TestClient(app)
        response = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "invalid.token.value"},
        )
        assert response.status_code == 401

    def test_refresh_missing_token(self) -> None:
        """Missing refresh_token field should return 422."""
        client = TestClient(app)
        response = client.post(
            "/api/v1/auth/refresh",
            json={},
        )
        assert response.status_code == 422


class TestRateLimiting:
    """Integration tests for rate limiting on auth endpoints."""

    def test_rate_limiting_auth_endpoint(self) -> None:
        """Auth endpoints should return 429 after exceeding rate limit."""
        import app.api.middleware.rate_limit as rl_module
        from app.api.middleware.rate_limit import RateLimitStore

        original_store = rl_module._rate_limit_store
        rl_module._rate_limit_store = RateLimitStore()

        # Provide a DB override so requests that pass rate limit don't hit real DB
        app.dependency_overrides[get_db] = _make_db_override(None)

        try:
            client = TestClient(app)
            responses = []
            for _ in range(12):
                resp = client.post(
                    "/api/v1/auth/token",
                    json={"email": "test@example.com", "password": "testpass123"},
                )
                responses.append(resp.status_code)

            # At least one response should be 429 (rate limited)
            assert 429 in responses
        finally:
            rl_module._rate_limit_store = original_store

    def test_non_auth_endpoint_not_rate_limited(self) -> None:
        """Non-auth endpoints should not be rate limited."""
        client = TestClient(app)
        for _ in range(20):
            resp = client.get("/health")
            assert resp.status_code == 200
