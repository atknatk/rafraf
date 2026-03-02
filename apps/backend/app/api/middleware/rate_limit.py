"""Rate limiting middleware using in-memory store (Redis upgrade path available)."""

import time
from collections import defaultdict

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import get_settings

logger: structlog.stdlib.BoundLogger = structlog.get_logger()


class RateLimitStore:
    """In-memory rate limit tracker.

    Tracks request counts per IP with a sliding window.
    Can be replaced with Redis for multi-instance deployments.
    """

    def __init__(self) -> None:
        self._requests: dict[str, list[float]] = defaultdict(list)

    def is_rate_limited(self, key: str, max_requests: int, window_seconds: int) -> bool:
        """Check if a key has exceeded the rate limit.

        Args:
            key: The rate limit key (e.g., IP address).
            max_requests: Maximum allowed requests in the window.
            window_seconds: Time window in seconds.

        Returns:
            True if the key is rate limited.
        """
        now = time.monotonic()
        cutoff = now - window_seconds

        # Remove expired entries
        self._requests[key] = [t for t in self._requests[key] if t > cutoff]

        if len(self._requests[key]) >= max_requests:
            return True

        self._requests[key].append(now)
        return False


# Module-level store (single instance per process)
_rate_limit_store = RateLimitStore()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware for auth endpoints.

    Applies rate limiting to /api/v1/auth/* paths only.
    """

    def __init__(
        self,
        app: object,
        rate_limit_store: RateLimitStore | None = None,
    ) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._store = rate_limit_store or _rate_limit_store

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """Apply rate limiting to auth endpoints."""
        path = request.url.path

        # Only rate limit auth endpoints
        if not path.startswith("/api/v1/auth/"):
            return await call_next(request)

        settings = get_settings()
        client_ip = self._get_client_ip(request)
        rate_limit_key = f"auth:{client_ip}"

        if self._store.is_rate_limited(
            key=rate_limit_key,
            max_requests=settings.rate_limit_requests_per_minute,
            window_seconds=60,
        ):
            await logger.awarning(
                "rate_limit_exceeded",
                client_ip=client_ip,
                path=path,
            )
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please try again later."},
            )

        return await call_next(request)

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP from request, considering X-Forwarded-For."""
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        client = request.client
        if client is not None:
            return client.host
        return "unknown"
