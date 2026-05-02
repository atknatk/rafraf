"""JWT authentication and security utilities.

T2.9 (Faz 2) — JWT RS256 migration:

- New tokens are signed with RS256 (asymmetric) using ``jwt_private_key_path``.
- Verification tries RS256 first using ``jwt_public_key_path``.
- If verification fails, the legacy HS256 secret is tried as a fallback,
  but only while the current time is BEFORE ``jwt_legacy_grace_until``.
- After the grace period, HS256 tokens are rejected and the rejection is
  logged as ``legacy_hs256_token_rejected_post_grace`` for observability.

Key files are loaded once at import time (via the cached helpers below).
A missing private key path is tolerated at import time but raises
``SecurityError`` when an attempt is made to sign a token (so the process
boots even if signing keys are not yet mounted).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path

import bcrypt
import structlog
from jose import JWTError, jwt

from app.core.config import get_settings

logger: structlog.stdlib.BoundLogger = structlog.get_logger()


class SecurityError(Exception):
    """Security-related error."""


# ---------------------------------------------------------------------------
# Password hashing (unchanged from V1)
# ---------------------------------------------------------------------------


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8"),
    )


# ---------------------------------------------------------------------------
# Key loading (cached at module level — refreshable via reset_key_cache())
# ---------------------------------------------------------------------------


@lru_cache(maxsize=2)
def _load_pem(path: str) -> str:
    """Load a PEM file from disk and cache its contents.

    Raises:
        SecurityError: If the file does not exist or cannot be read.
    """
    pem_path = Path(path)
    if not pem_path.is_file():
        msg = f"PEM key file not found: {path}"
        raise SecurityError(msg)
    try:
        return pem_path.read_text(encoding="utf-8")
    except OSError as exc:  # pragma: no cover — defensive
        msg = f"Failed to read PEM key {path}: {exc}"
        raise SecurityError(msg) from exc


def _get_private_key() -> str:
    """Return the cached RS256 private key (PEM).

    Raises:
        SecurityError: If the key path is unset or the file is missing.
    """
    settings = get_settings()
    if not settings.jwt_private_key_path:
        msg = (
            "JWT_PRIVATE_KEY_PATH is not configured — cannot sign RS256 tokens. "
            "Set the env var or run infra/scripts/generate-jwt-keys.sh."
        )
        raise SecurityError(msg)
    return _load_pem(settings.jwt_private_key_path)


def _get_public_key() -> str | None:
    """Return the cached RS256 public key (PEM) or ``None`` if unset."""
    settings = get_settings()
    if not settings.jwt_public_key_path:
        return None
    return _load_pem(settings.jwt_public_key_path)


def reset_key_cache() -> None:
    """Clear the PEM cache. Intended for tests / SIGHUP-style key rotation."""
    _load_pem.cache_clear()


# ---------------------------------------------------------------------------
# Algorithm selection helpers
# ---------------------------------------------------------------------------


def _is_hs_algorithm(alg: str) -> bool:
    """Return True for HMAC-family algorithms (legacy HS256 etc.)."""
    return alg.upper().startswith("HS")


def _is_rs_algorithm(alg: str) -> bool:
    """Return True for RSA-family algorithms (RS256 etc.)."""
    return alg.upper().startswith("RS")


def _signing_key_and_alg() -> tuple[str, str]:
    """Resolve signing key + algorithm based on settings.

    Defaults to RS256 with private key from disk. If the configured algorithm
    is HS-family, falls back to ``jwt_secret_key`` (DEPRECATED — kept for
    backward compat during the grace period).

    Raises:
        SecurityError: If RS256 is configured without a private key path.
    """
    settings = get_settings()
    alg = settings.jwt_algorithm
    if _is_rs_algorithm(alg):
        return _get_private_key(), alg
    if _is_hs_algorithm(alg):
        return settings.jwt_secret_key, alg
    msg = f"Unsupported JWT algorithm: {alg}"
    raise SecurityError(msg)


# ---------------------------------------------------------------------------
# Token creation
# ---------------------------------------------------------------------------


def create_access_token(
    subject: str,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a JWT access token for the given subject.

    Signs with the configured algorithm (RS256 by default; HS256 for legacy
    deployments). Algorithm + key source are observable via structured logs.
    """
    settings = get_settings()
    now = datetime.now(tz=UTC)
    expire = now + (expires_delta or timedelta(minutes=settings.jwt_access_token_expire_minutes))
    to_encode: dict[str, object] = {
        "sub": subject,
        "type": "access",
        "exp": expire,
        "iat": now,
    }
    key, alg = _signing_key_and_alg()
    token: str = jwt.encode(to_encode, key, algorithm=alg)
    logger.debug("jwt_token_signed", token_type="access", algorithm=alg, subject=subject)
    return token


def create_refresh_token(
    subject: str,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a JWT refresh token for the given subject."""
    settings = get_settings()
    now = datetime.now(tz=UTC)
    expire = now + (expires_delta or timedelta(days=settings.jwt_refresh_token_expire_days))
    to_encode: dict[str, object] = {
        "sub": subject,
        "type": "refresh",
        "exp": expire,
        "iat": now,
    }
    key, alg = _signing_key_and_alg()
    token: str = jwt.encode(to_encode, key, algorithm=alg)
    logger.debug("jwt_token_signed", token_type="refresh", algorithm=alg, subject=subject)
    return token


# ---------------------------------------------------------------------------
# Token verification — RS256 first, HS256 fallback during grace period
# ---------------------------------------------------------------------------


def _hs256_grace_active() -> bool:
    """Return True if the HS256 grace period is still active."""
    settings = get_settings()
    if settings.jwt_legacy_grace_until is None:
        return False
    deadline = settings.jwt_legacy_grace_until
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=UTC)
    return datetime.now(tz=UTC) < deadline


def _hs256_secret() -> str | None:
    """Return the HS256 verification secret (only the explicit legacy secret).

    T2.9-fix (M2): no longer falls back to ``jwt_secret_key``. The deprecated
    ``jwt_secret_key`` field has a non-empty Pydantic default which would make
    every deployment look like it has a legacy HS256 secret configured, masking
    operator misconfiguration and inflating the post-grace warning rate.
    Operators must explicitly set ``JWT_LEGACY_HS256_SECRET`` to opt into HS256
    verification during the migration window.
    """
    settings = get_settings()
    return settings.jwt_legacy_hs256_secret or None


_jwt_settings_warning_emitted = False


def warn_if_deprecated_jwt_secret_only() -> None:
    """Emit a one-shot startup warning if jwt_secret_key is set without legacy.

    T2.9-fix (M2 follow-up): if an operator left the deprecated
    ``JWT_SECRET_KEY`` env var set without configuring
    ``JWT_LEGACY_HS256_SECRET``, the deployment will silently REJECT all
    legacy HS256 tokens (because we no longer fall back to ``jwt_secret_key``).
    Surface this misconfiguration loudly at startup so operators can either
    migrate the value to ``JWT_LEGACY_HS256_SECRET`` or remove the deprecated
    env var entirely.
    """
    global _jwt_settings_warning_emitted  # noqa: PLW0603
    if _jwt_settings_warning_emitted:
        return
    settings = get_settings()
    # Only warn when the deprecated key is explicitly customized AND no legacy
    # secret is configured. If both are unset (or jwt_secret_key matches the
    # default and no one cares about HS256), stay silent.
    deprecated_default = "dev-secret-change-in-production"
    deprecated_set = bool(settings.jwt_secret_key) and settings.jwt_secret_key != deprecated_default
    legacy_unset = settings.jwt_legacy_hs256_secret is None
    if deprecated_set and legacy_unset:
        logger.warning(
            "jwt_secret_key_set_but_legacy_unset",
            note=(
                "JWT_SECRET_KEY is set but JWT_LEGACY_HS256_SECRET is not. "
                "Legacy HS256 tokens will be REJECTED. Either move the value "
                "to JWT_LEGACY_HS256_SECRET (during the grace period) or "
                "remove the deprecated JWT_SECRET_KEY env var."
            ),
        )
    _jwt_settings_warning_emitted = True


def _reset_jwt_warning_flag_for_tests() -> None:
    """Reset the one-shot startup warning flag. Test-only."""
    global _jwt_settings_warning_emitted  # noqa: PLW0603
    _jwt_settings_warning_emitted = False


def decode_access_token(token: str) -> dict[str, object]:
    """Decode + verify a JWT access token.

    Tries RS256 first (using ``jwt_public_key_path``), then falls back to
    HS256 verification IFF the grace period has not yet expired. Returns the
    decoded payload as a dict.

    Raises:
        SecurityError: If the token cannot be verified by any active method.
    """
    return _decode_token(token, expected_type="access")


def decode_refresh_token(token: str) -> dict[str, object]:
    """Decode + verify a JWT refresh token. See :func:`decode_access_token`."""
    return _decode_token(token, expected_type="refresh")


def _decode_token(token: str, *, expected_type: str) -> dict[str, object]:
    """Internal: decode a token and validate the ``type`` claim.

    Order of attempts:
      1. RS256 (if a public key is configured)
      2. HS256 (if a legacy secret is configured AND the grace period is active)

    Logs the algorithm that ultimately succeeded, plus a warning whenever
    the HS256 fallback is used (so we can observe migration progress).
    """
    public_key = _get_public_key()
    rs_error: JWTError | None = None
    payload: dict[str, object] | None = None
    used_alg: str | None = None

    if public_key is not None:
        try:
            payload = jwt.decode(token, public_key, algorithms=["RS256"])
            used_alg = "RS256"
        except JWTError as exc:
            rs_error = exc

    if payload is None:
        # Try HS256 fallback only during the grace period.
        hs_secret = _hs256_secret()
        if hs_secret is not None and _hs256_grace_active():
            try:
                payload = jwt.decode(token, hs_secret, algorithms=["HS256"])
                used_alg = "HS256"
                logger.warning(
                    "legacy_hs256_token_accepted",
                    token_type=expected_type,
                    note="HS256 token accepted during grace period",
                )
            except JWTError as exc:
                msg = f"Token verification failed: {exc}"
                raise SecurityError(msg) from exc
        else:
            # Outside grace period (or no legacy secret configured) — reject.
            #
            # T2.9-fix (M1): the post-grace warning must fire ONLY when the
            # token actually claims ``alg=HS256``. Before this fix the warning
            # fired on EVERY failed RS256 verification (including routine
            # token expiry), inflating the alert rate operators were told to
            # page on. Inspect the token header (no signature check) and only
            # log when (a) operator explicitly configured a legacy secret,
            # (b) we are past the grace deadline, and (c) the token is HS256.
            settings = get_settings()
            if (
                settings.jwt_legacy_hs256_secret is not None
                and not _hs256_grace_active()
            ):
                try:
                    alg = jwt.get_unverified_header(token).get("alg")
                except JWTError:
                    alg = None
                if alg == "HS256":
                    logger.warning(
                        "legacy_hs256_token_rejected_post_grace",
                        token_type=expected_type,
                        note="HS256 fallback disabled (grace period expired)",
                    )
            if rs_error is not None:
                err_msg = f"Token verification failed: {rs_error}"
            else:
                err_msg = "Token verification failed"
            raise SecurityError(err_msg) from rs_error

    # Common claim validation
    subject = payload.get("sub")
    token_type = payload.get("type")
    if subject is None or not isinstance(subject, str):
        msg = "Token payload missing subject"
        raise SecurityError(msg)
    if token_type != expected_type:
        msg = f"Token is not a{'n' if expected_type == 'access' else ''} {expected_type} token"
        raise SecurityError(msg)

    logger.debug(
        "jwt_token_verified",
        token_type=expected_type,
        algorithm=used_alg,
        subject=subject,
    )
    return payload


# ---------------------------------------------------------------------------
# Backward-compatible helpers (return the subject string)
# ---------------------------------------------------------------------------


def verify_access_token(token: str) -> str:
    """Verify a JWT access token and return the subject.

    Backward-compatible wrapper around :func:`decode_access_token` —
    callers that only need the subject can keep using this function.

    Raises:
        SecurityError: If the token is invalid, expired, or not an access token.
    """
    payload = decode_access_token(token)
    subject = payload["sub"]
    assert isinstance(subject, str)  # noqa: S101 — guaranteed by _decode_token
    return subject


def verify_refresh_token(token: str) -> str:
    """Verify a JWT refresh token and return the subject.

    Raises:
        SecurityError: If the token is invalid, expired, or not a refresh token.
    """
    payload = decode_refresh_token(token)
    subject = payload["sub"]
    assert isinstance(subject, str)  # noqa: S101 — guaranteed by _decode_token
    return subject


__all__ = [
    "SecurityError",
    "create_access_token",
    "create_refresh_token",
    "decode_access_token",
    "decode_refresh_token",
    "hash_password",
    "reset_key_cache",
    "verify_access_token",
    "verify_password",
    "verify_refresh_token",
    "warn_if_deprecated_jwt_secret_only",
]
