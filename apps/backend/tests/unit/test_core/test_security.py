"""Unit tests for JWT security utilities."""

from datetime import timedelta

import pytest
from jose import jwt

from app.core.config import get_settings
from app.core.security import (
    SecurityError,
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_access_token,
    verify_password,
    verify_refresh_token,
)


class TestPasswordHashing:
    """Tests for password hashing and verification."""

    def test_hash_password_returns_hashed_string(self) -> None:
        """hash_password should return a bcrypt hash string."""
        hashed = hash_password("testpassword123")
        assert hashed != "testpassword123"
        assert hashed.startswith("$2b$")

    def test_verify_password_correct(self) -> None:
        """verify_password should return True for correct password."""
        hashed = hash_password("testpassword123")
        assert verify_password("testpassword123", hashed) is True

    def test_verify_password_incorrect(self) -> None:
        """verify_password should return False for incorrect password."""
        hashed = hash_password("testpassword123")
        assert verify_password("wrongpassword", hashed) is False

    def test_hash_password_unique_hashes(self) -> None:
        """hash_password should generate different hashes for same input."""
        hash1 = hash_password("testpassword123")
        hash2 = hash_password("testpassword123")
        assert hash1 != hash2  # bcrypt uses random salt


class TestAccessToken:
    """Tests for access token creation and verification."""

    def test_create_access_token_returns_string(self) -> None:
        """create_access_token should return a JWT string."""
        token = create_access_token(subject="user-123")
        assert isinstance(token, str)
        assert len(token) > 0

    def test_create_access_token_contains_subject(self) -> None:
        """create_access_token should embed the subject in payload."""
        token = create_access_token(subject="user-123")
        payload = jwt.decode(token, get_settings().jwt_secret_key, algorithms=["HS256"])
        assert payload["sub"] == "user-123"

    def test_create_access_token_contains_type_field(self) -> None:
        """create_access_token should set type to 'access'."""
        token = create_access_token(subject="user-123")
        payload = jwt.decode(token, get_settings().jwt_secret_key, algorithms=["HS256"])
        assert payload["type"] == "access"

    def test_create_access_token_contains_exp_and_iat(self) -> None:
        """create_access_token should include exp and iat claims."""
        token = create_access_token(subject="user-123")
        payload = jwt.decode(token, get_settings().jwt_secret_key, algorithms=["HS256"])
        assert "exp" in payload
        assert "iat" in payload

    def test_create_access_token_custom_expiry(self) -> None:
        """create_access_token should accept custom expiry delta."""
        token = create_access_token(
            subject="user-123",
            expires_delta=timedelta(minutes=5),
        )
        payload = jwt.decode(token, get_settings().jwt_secret_key, algorithms=["HS256"])
        assert payload["exp"] - payload["iat"] == 300

    def test_verify_access_token_valid(self) -> None:
        """verify_access_token should return subject for valid token."""
        token = create_access_token(subject="user-123")
        result = verify_access_token(token)
        assert result == "user-123"

    def test_verify_access_token_expired_raises(self) -> None:
        """verify_access_token should raise SecurityError for expired token."""
        token = create_access_token(
            subject="user-123",
            expires_delta=timedelta(seconds=-1),
        )
        with pytest.raises(SecurityError, match="Token verification failed"):
            verify_access_token(token)

    def test_verify_access_token_invalid_string_raises(self) -> None:
        """verify_access_token should raise SecurityError for invalid token."""
        with pytest.raises(SecurityError, match="Token verification failed"):
            verify_access_token("invalid.token.string")

    def test_verify_access_token_rejects_refresh_token(self) -> None:
        """verify_access_token should reject a refresh token."""
        token = create_refresh_token(subject="user-123")
        with pytest.raises(SecurityError, match="not an access token"):
            verify_access_token(token)

    def test_verify_access_token_missing_subject_raises(self) -> None:
        """verify_access_token should raise SecurityError when subject is missing."""
        # Create a token without 'sub' claim
        payload = {"type": "access", "exp": 9999999999, "iat": 1000000000}
        token = jwt.encode(payload, get_settings().jwt_secret_key, algorithm="HS256")
        with pytest.raises(SecurityError, match="missing subject"):
            verify_access_token(token)


class TestRefreshToken:
    """Tests for refresh token creation and verification."""

    def test_create_refresh_token_returns_string(self) -> None:
        """create_refresh_token should return a JWT string."""
        token = create_refresh_token(subject="user-123")
        assert isinstance(token, str)
        assert len(token) > 0

    def test_create_refresh_token_contains_type_field(self) -> None:
        """create_refresh_token should set type to 'refresh'."""
        token = create_refresh_token(subject="user-123")
        payload = jwt.decode(token, get_settings().jwt_secret_key, algorithms=["HS256"])
        assert payload["type"] == "refresh"

    def test_verify_refresh_token_valid(self) -> None:
        """verify_refresh_token should return subject for valid token."""
        token = create_refresh_token(subject="user-456")
        result = verify_refresh_token(token)
        assert result == "user-456"

    def test_verify_refresh_token_expired_raises(self) -> None:
        """verify_refresh_token should raise SecurityError for expired token."""
        token = create_refresh_token(
            subject="user-123",
            expires_delta=timedelta(seconds=-1),
        )
        with pytest.raises(SecurityError, match="Token verification failed"):
            verify_refresh_token(token)

    def test_verify_refresh_token_rejects_access_token(self) -> None:
        """verify_refresh_token should reject an access token."""
        token = create_access_token(subject="user-123")
        with pytest.raises(SecurityError, match="not a refresh token"):
            verify_refresh_token(token)

    def test_verify_refresh_token_invalid_string_raises(self) -> None:
        """verify_refresh_token should raise SecurityError for invalid token."""
        with pytest.raises(SecurityError, match="Token verification failed"):
            verify_refresh_token("garbage.token.value")

    def test_create_refresh_token_custom_expiry(self) -> None:
        """create_refresh_token should accept custom expiry delta."""
        token = create_refresh_token(
            subject="user-123",
            expires_delta=timedelta(days=1),
        )
        payload = jwt.decode(token, get_settings().jwt_secret_key, algorithms=["HS256"])
        assert payload["exp"] - payload["iat"] == 86400
