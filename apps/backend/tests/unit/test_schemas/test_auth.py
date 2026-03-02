"""Unit tests for auth Pydantic schemas."""

import pytest
from pydantic import ValidationError

from app.schemas.auth import RefreshRequest, TokenRequest, TokenResponse, UserResponse


class TestTokenRequest:
    """Tests for TokenRequest schema validation."""

    def test_valid_token_request(self) -> None:
        """TokenRequest should accept valid email and password."""
        req = TokenRequest(email="user@example.com", password="secret123")
        assert req.email == "user@example.com"
        assert req.password == "secret123"

    def test_token_request_invalid_email(self) -> None:
        """TokenRequest should reject invalid email format."""
        with pytest.raises(ValidationError):
            TokenRequest(email="not-an-email", password="secret123")

    def test_token_request_empty_password(self) -> None:
        """TokenRequest should reject empty password."""
        with pytest.raises(ValidationError):
            TokenRequest(email="user@example.com", password="")

    def test_token_request_missing_email(self) -> None:
        """TokenRequest should require email field."""
        with pytest.raises(ValidationError):
            TokenRequest(password="secret123")  # type: ignore[call-arg]

    def test_token_request_missing_password(self) -> None:
        """TokenRequest should require password field."""
        with pytest.raises(ValidationError):
            TokenRequest(email="user@example.com")  # type: ignore[call-arg]


class TestRefreshRequest:
    """Tests for RefreshRequest schema validation."""

    def test_valid_refresh_request(self) -> None:
        """RefreshRequest should accept a refresh_token string."""
        req = RefreshRequest(refresh_token="abc123")
        assert req.refresh_token == "abc123"

    def test_refresh_request_missing_token(self) -> None:
        """RefreshRequest should require refresh_token field."""
        with pytest.raises(ValidationError):
            RefreshRequest()  # type: ignore[call-arg]


class TestTokenResponse:
    """Tests for TokenResponse schema."""

    def test_valid_token_response(self) -> None:
        """TokenResponse should store all token fields."""
        resp = TokenResponse(
            access_token="access-abc",
            refresh_token="refresh-xyz",
            token_type="bearer",
            expires_in=900,
        )
        assert resp.access_token == "access-abc"
        assert resp.refresh_token == "refresh-xyz"
        assert resp.token_type == "bearer"
        assert resp.expires_in == 900

    def test_token_response_default_type(self) -> None:
        """TokenResponse should default token_type to 'bearer'."""
        resp = TokenResponse(
            access_token="access-abc",
            refresh_token="refresh-xyz",
            expires_in=900,
        )
        assert resp.token_type == "bearer"


class TestUserResponse:
    """Tests for UserResponse schema."""

    def test_valid_user_response(self) -> None:
        """UserResponse should store user info."""
        resp = UserResponse(
            id="123e4567-e89b-12d3-a456-426614174000",
            email="user@example.com",
            is_active=True,
            created_at="2026-03-02T10:00:00Z",
        )
        assert resp.id == "123e4567-e89b-12d3-a456-426614174000"
        assert resp.email == "user@example.com"
        assert resp.is_active is True

    def test_user_response_is_frozen(self) -> None:
        """UserResponse should be immutable (frozen)."""
        resp = UserResponse(
            id="123",
            email="user@example.com",
            is_active=True,
            created_at="2026-03-02T10:00:00Z",
        )
        with pytest.raises(ValidationError):
            resp.email = "other@example.com"  # type: ignore[misc]
