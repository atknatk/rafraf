"""JWT authentication and security utilities."""

from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class SecurityError(Exception):
    """Security-related error."""


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    hashed: str = pwd_context.hash(password)
    return hashed


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    result: bool = pwd_context.verify(plain_password, hashed_password)
    return result


def create_access_token(
    subject: str,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a JWT access token for the given subject."""
    settings = get_settings()
    now = datetime.now(tz=UTC)
    expire = now + (expires_delta or timedelta(minutes=settings.jwt_access_token_expire_minutes))
    to_encode = {"sub": subject, "type": "access", "exp": expire, "iat": now}
    return jwt.encode(  # type: ignore[no-any-return]
        to_encode,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def create_refresh_token(
    subject: str,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a JWT refresh token for the given subject."""
    settings = get_settings()
    now = datetime.now(tz=UTC)
    expire = now + (expires_delta or timedelta(days=settings.jwt_refresh_token_expire_days))
    to_encode = {"sub": subject, "type": "refresh", "exp": expire, "iat": now}
    return jwt.encode(  # type: ignore[no-any-return]
        to_encode,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def verify_access_token(token: str) -> str:
    """Verify a JWT access token and return the subject.

    Raises:
        SecurityError: If the token is invalid, expired, or not an access token.
    """
    settings = get_settings()
    try:
        payload: dict[str, object] = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        subject = payload.get("sub")
        token_type = payload.get("type")
        if subject is None or not isinstance(subject, str):
            msg = "Token payload missing subject"
            raise SecurityError(msg)
        if token_type != "access":
            msg = "Token is not an access token"
            raise SecurityError(msg)
        return subject
    except JWTError as exc:
        msg = f"Token verification failed: {exc}"
        raise SecurityError(msg) from exc


def verify_refresh_token(token: str) -> str:
    """Verify a JWT refresh token and return the subject.

    Raises:
        SecurityError: If the token is invalid, expired, or not a refresh token.
    """
    settings = get_settings()
    try:
        payload: dict[str, object] = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        subject = payload.get("sub")
        token_type = payload.get("type")
        if subject is None or not isinstance(subject, str):
            msg = "Token payload missing subject"
            raise SecurityError(msg)
        if token_type != "refresh":
            msg = "Token is not a refresh token"
            raise SecurityError(msg)
        return subject
    except JWTError as exc:
        msg = f"Token verification failed: {exc}"
        raise SecurityError(msg) from exc
