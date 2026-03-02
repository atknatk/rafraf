"""JWT authentication and security utilities."""

from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt

from app.core.config import get_settings


class SecurityError(Exception):
    """Security-related error."""


def create_access_token(
    subject: str,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a JWT access token for the given subject."""
    settings = get_settings()
    now = datetime.now(tz=UTC)
    expire = now + (expires_delta or timedelta(minutes=settings.jwt_access_token_expire_minutes))
    to_encode = {"sub": subject, "exp": expire, "iat": now}
    return jwt.encode(  # type: ignore[no-any-return]
        to_encode,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def verify_access_token(token: str) -> str:
    """Verify a JWT access token and return the subject.

    Raises:
        SecurityError: If the token is invalid or expired.
    """
    settings = get_settings()
    try:
        payload: dict[str, object] = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        subject = payload.get("sub")
        if subject is None or not isinstance(subject, str):
            msg = "Token payload missing subject"
            raise SecurityError(msg)
        return subject
    except JWTError as exc:
        msg = f"Token verification failed: {exc}"
        raise SecurityError(msg) from exc
