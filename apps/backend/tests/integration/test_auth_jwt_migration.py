"""Integration smoke tests for JWT RS256 migration (T2.9).

Verifies the end-to-end migration scenario:
  1. Backend issues an RS256 token via the login endpoint.
  2. The same token authenticates a subsequent protected request.
  3. A token forged under the legacy HS256 secret still authenticates
     while the grace period is active.
  4. After the grace deadline, HS256 tokens are rejected with 401.

These tests piggy-back on the session-scoped RSA keypair fixture in
``tests/conftest.py``.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator, Iterator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.config import get_settings
from app.core.security import hash_password, reset_key_cache
from app.main import app

EMAIL = "migrate@example.com"
PASSWORD = "migrationtest123"


def _mock_user(user_id: uuid.UUID, *, is_active: bool = True) -> MagicMock:
    user = MagicMock()
    user.id = user_id
    user.email = EMAIL
    user.hashed_password = hash_password(PASSWORD)
    user.is_active = is_active
    user.display_name = "Migration Tester"
    # `created_at.isoformat()` is called by the route, so mock that too.
    fake_now = datetime(2026, 5, 1, tzinfo=UTC)
    user.created_at = fake_now
    return user


def _db_override(user: MagicMock | None) -> object:
    mock_session = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    result.scalar_one_or_none.return_value = user
    mock_session.execute = AsyncMock(return_value=result)
    mock_session.flush = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()

    async def override() -> AsyncGenerator[AsyncSession, None]:
        yield mock_session  # type: ignore[misc]

    return override


@pytest.fixture(autouse=True)
def _clear_overrides() -> Iterator[None]:
    """Reset rate-limit counters, clear DI overrides, restore JWT settings.

    The RateLimitMiddleware caches the store reference at construction time,
    so we MUST clear the existing instance's counters in-place rather than
    swap in a new store (which the middleware would ignore).
    """
    import app.api.middleware.rate_limit as rl_module

    rl_module._rate_limit_store._requests.clear()

    settings = get_settings()
    snapshot = {
        "jwt_legacy_grace_until": settings.jwt_legacy_grace_until,
        "jwt_legacy_hs256_secret": settings.jwt_legacy_hs256_secret,
    }
    try:
        yield
    finally:
        app.dependency_overrides.clear()
        rl_module._rate_limit_store._requests.clear()
        for k, v in snapshot.items():
            setattr(settings, k, v)
        reset_key_cache()


def _hs256_secret() -> str:
    settings = get_settings()
    return settings.jwt_legacy_hs256_secret or settings.jwt_secret_key


def _forge_hs256_access_token(user_id: uuid.UUID, ttl_minutes: int = 15) -> str:
    """Create a token signed with the legacy HS256 secret (simulates a pre-T2.9 token)."""
    now = datetime.now(tz=UTC)
    payload: dict[str, object] = {
        "sub": str(user_id),
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=ttl_minutes),
    }
    return jwt.encode(payload, _hs256_secret(), algorithm="HS256")


class TestRs256RoundTrip:
    """End-to-end: login → use issued RS256 token on a protected route."""

    def test_issued_token_is_rs256(self) -> None:
        user_id = uuid.uuid4()
        app.dependency_overrides[get_db] = _db_override(_mock_user(user_id))
        client = TestClient(app)

        response = client.post(
            "/api/v1/auth/token",
            json={"email": EMAIL, "password": PASSWORD},
        )
        assert response.status_code == 200
        access_token = response.json()["access_token"]

        header = jwt.get_unverified_header(access_token)
        assert header["alg"] == "RS256", (
            "T2.9: tokens issued by the backend MUST be signed with RS256"
        )

    def test_rs256_token_authenticates_protected_route(self) -> None:
        user_id = uuid.uuid4()
        app.dependency_overrides[get_db] = _db_override(_mock_user(user_id))
        client = TestClient(app)

        login = client.post(
            "/api/v1/auth/token",
            json={"email": EMAIL, "password": PASSWORD},
        )
        access_token = login.json()["access_token"]

        # GET /api/v1/auth/profile — uses get_current_user dependency.
        me = client.get(
            "/api/v1/auth/profile",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert me.status_code == 200, me.text
        assert me.json()["email"] == EMAIL


class TestHs256GracePeriodIntegration:
    """Verify HS256 fallback behavior end-to-end against /auth/me."""

    def test_hs256_token_works_during_grace_period(self) -> None:
        settings = get_settings()
        settings.jwt_legacy_grace_until = datetime.now(tz=UTC) + timedelta(days=1)

        user_id = uuid.uuid4()
        app.dependency_overrides[get_db] = _db_override(_mock_user(user_id))
        client = TestClient(app)

        legacy_token = _forge_hs256_access_token(user_id)
        response = client.get(
            "/api/v1/auth/profile",
            headers={"Authorization": f"Bearer {legacy_token}"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["email"] == EMAIL

    def test_hs256_token_rejected_after_grace_period(self) -> None:
        settings = get_settings()
        settings.jwt_legacy_grace_until = datetime.now(tz=UTC) - timedelta(seconds=1)

        user_id = uuid.uuid4()
        app.dependency_overrides[get_db] = _db_override(_mock_user(user_id))
        client = TestClient(app)

        legacy_token = _forge_hs256_access_token(user_id)
        response = client.get(
            "/api/v1/auth/profile",
            headers={"Authorization": f"Bearer {legacy_token}"},
        )
        assert response.status_code == 401
