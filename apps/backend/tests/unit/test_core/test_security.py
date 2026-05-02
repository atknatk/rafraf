"""Unit tests for JWT security utilities.

Covers password hashing, RS256 token round-trips, and the HS256 grace
period (T2.9). The session-scoped fixture in ``tests/conftest.py``
generates an RSA keypair and wires it into the cached ``Settings``
singleton, so every test in this module runs against RS256 by default.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from jose import jwt

from app.core.config import get_settings
from app.core.security import (
    SecurityError,
    create_access_token,
    create_refresh_token,
    decode_access_token,
    hash_password,
    reset_key_cache,
    verify_access_token,
    verify_password,
    verify_refresh_token,
)

if TYPE_CHECKING:
    from collections.abc import Iterator


def _hs256_secret() -> str:
    """Return the HS256 secret used by tests (legacy fallback secret)."""
    settings = get_settings()
    return settings.jwt_legacy_hs256_secret or settings.jwt_secret_key


def _public_key_pem() -> str:
    """Return the test RS256 public key as PEM text."""
    settings = get_settings()
    assert settings.jwt_public_key_path is not None
    return Path(settings.jwt_public_key_path).read_text(encoding="utf-8")


@pytest.fixture
def _restore_settings() -> Iterator[None]:
    """Snapshot mutable JWT settings, restore them after the test."""
    settings = get_settings()
    snapshot = {
        "jwt_algorithm": settings.jwt_algorithm,
        "jwt_legacy_hs256_secret": settings.jwt_legacy_hs256_secret,
        "jwt_legacy_grace_until": settings.jwt_legacy_grace_until,
        "jwt_private_key_path": settings.jwt_private_key_path,
        "jwt_public_key_path": settings.jwt_public_key_path,
    }
    try:
        yield
    finally:
        for k, v in snapshot.items():
            setattr(settings, k, v)
        reset_key_cache()


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
    """Tests for access token creation and verification (RS256 default)."""

    def test_create_access_token_returns_string(self) -> None:
        """create_access_token should return a JWT string."""
        token = create_access_token(subject="user-123")
        assert isinstance(token, str)
        assert len(token) > 0

    def test_create_access_token_uses_rs256_by_default(self) -> None:
        """create_access_token should sign with RS256 by default (T2.9)."""
        token = create_access_token(subject="user-123")
        header = jwt.get_unverified_header(token)
        assert header["alg"] == "RS256"

    def test_create_access_token_contains_subject(self) -> None:
        """create_access_token should embed the subject in payload."""
        token = create_access_token(subject="user-123")
        payload = jwt.decode(token, _public_key_pem(), algorithms=["RS256"])
        assert payload["sub"] == "user-123"

    def test_create_access_token_contains_type_field(self) -> None:
        """create_access_token should set type to 'access'."""
        token = create_access_token(subject="user-123")
        payload = jwt.decode(token, _public_key_pem(), algorithms=["RS256"])
        assert payload["type"] == "access"

    def test_create_access_token_contains_exp_and_iat(self) -> None:
        """create_access_token should include exp and iat claims."""
        token = create_access_token(subject="user-123")
        payload = jwt.decode(token, _public_key_pem(), algorithms=["RS256"])
        assert "exp" in payload
        assert "iat" in payload

    def test_create_access_token_custom_expiry(self) -> None:
        """create_access_token should accept custom expiry delta."""
        token = create_access_token(
            subject="user-123",
            expires_delta=timedelta(minutes=5),
        )
        payload = jwt.decode(token, _public_key_pem(), algorithms=["RS256"])
        assert payload["exp"] - payload["iat"] == 300

    def test_verify_access_token_valid(self) -> None:
        """verify_access_token should return subject for valid token."""
        token = create_access_token(subject="user-123")
        result = verify_access_token(token)
        assert result == "user-123"

    def test_decode_access_token_round_trip(self) -> None:
        """decode_access_token should round-trip an RS256 token."""
        token = create_access_token(subject="round-trip-user")
        payload = decode_access_token(token)
        assert payload["sub"] == "round-trip-user"
        assert payload["type"] == "access"

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
        # Create a token without 'sub' claim, signed with RS256.
        settings = get_settings()
        assert settings.jwt_private_key_path is not None
        priv_pem = Path(settings.jwt_private_key_path).read_text(encoding="utf-8")
        payload = {"type": "access", "exp": 9999999999, "iat": 1000000000}
        token = jwt.encode(payload, priv_pem, algorithm="RS256")
        with pytest.raises(SecurityError, match="missing subject"):
            verify_access_token(token)


class TestRefreshToken:
    """Tests for refresh token creation and verification."""

    def test_create_refresh_token_returns_string(self) -> None:
        """create_refresh_token should return a JWT string."""
        token = create_refresh_token(subject="user-123")
        assert isinstance(token, str)
        assert len(token) > 0

    def test_create_refresh_token_uses_rs256(self) -> None:
        """create_refresh_token should sign with RS256."""
        token = create_refresh_token(subject="user-123")
        assert jwt.get_unverified_header(token)["alg"] == "RS256"

    def test_create_refresh_token_contains_type_field(self) -> None:
        """create_refresh_token should set type to 'refresh'."""
        token = create_refresh_token(subject="user-123")
        payload = jwt.decode(token, _public_key_pem(), algorithms=["RS256"])
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
        payload = jwt.decode(token, _public_key_pem(), algorithms=["RS256"])
        assert payload["exp"] - payload["iat"] == 86400


class TestHs256GracePeriod:
    """T2.9: HS256 fallback during the configured grace period."""

    def _make_hs256_token(
        self,
        subject: str = "user-hs",
        token_type: str = "access",
        ttl: timedelta = timedelta(minutes=15),
    ) -> str:
        """Forge an HS256 token using the configured legacy secret."""
        now = datetime.now(tz=UTC)
        payload: dict[str, object] = {
            "sub": subject,
            "type": token_type,
            "iat": now,
            "exp": now + ttl,
        }
        return jwt.encode(payload, _hs256_secret(), algorithm="HS256")

    @pytest.mark.usefixtures("_restore_settings")
    def test_hs256_token_accepted_during_grace(self) -> None:
        """An HS256 token should verify successfully while grace is active."""
        settings = get_settings()
        settings.jwt_legacy_grace_until = datetime.now(tz=UTC) + timedelta(days=1)
        token = self._make_hs256_token(subject="user-grace")
        assert verify_access_token(token) == "user-grace"

    @pytest.mark.usefixtures("_restore_settings")
    def test_hs256_token_rejected_after_grace(self) -> None:
        """After the grace deadline, HS256 tokens must be rejected."""
        settings = get_settings()
        settings.jwt_legacy_grace_until = datetime.now(tz=UTC) - timedelta(seconds=1)
        token = self._make_hs256_token(subject="user-late")
        with pytest.raises(SecurityError, match="Token verification failed"):
            verify_access_token(token)

    @pytest.mark.usefixtures("_restore_settings")
    def test_hs256_token_rejected_when_grace_unset(self) -> None:
        """If no grace deadline is configured, HS256 tokens are rejected."""
        settings = get_settings()
        settings.jwt_legacy_grace_until = None
        token = self._make_hs256_token(subject="user-no-grace")
        with pytest.raises(SecurityError, match="Token verification failed"):
            verify_access_token(token)

    @pytest.mark.usefixtures("_restore_settings")
    def test_rs256_token_still_accepted_in_grace_window(self) -> None:
        """RS256 tokens always verify; grace status doesn't affect them."""
        settings = get_settings()
        settings.jwt_legacy_grace_until = datetime.now(tz=UTC) + timedelta(days=1)
        token = create_access_token(subject="user-rs")
        assert verify_access_token(token) == "user-rs"


class TestKeyLoadingEdgeCases:
    """T2.9: graceful handling of misconfigured key paths."""

    @pytest.mark.usefixtures("_restore_settings")
    def test_missing_private_key_path_raises_security_error(self) -> None:
        """Signing without a configured private key path raises SecurityError."""
        settings = get_settings()
        settings.jwt_private_key_path = None
        reset_key_cache()
        with pytest.raises(SecurityError, match="JWT_PRIVATE_KEY_PATH"):
            create_access_token(subject="user-x")

    @pytest.mark.usefixtures("_restore_settings")
    def test_missing_private_key_file_raises_security_error(
        self, tmp_path: Path
    ) -> None:
        """A non-existent private key file should raise SecurityError, not crash."""
        settings = get_settings()
        settings.jwt_private_key_path = str(tmp_path / "does_not_exist.pem")
        reset_key_cache()
        with pytest.raises(SecurityError, match="PEM key file not found"):
            create_access_token(subject="user-y")

    @pytest.mark.usefixtures("_restore_settings")
    def test_verifier_only_mode_decodes_rs256(self) -> None:
        """A pod with only the public key (no private key) can still verify."""
        # First mint a token under the full keypair.
        token = create_access_token(subject="verifier-only-user")

        # Now simulate a verifier-only pod: no private key on disk.
        settings = get_settings()
        settings.jwt_private_key_path = None
        reset_key_cache()

        # Verification still works because the public key is present.
        assert verify_access_token(token) == "verifier-only-user"
