"""Rate limiting middleware using in-memory store (Redis upgrade path available)."""

import time
from collections import defaultdict

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import get_settings
from app.core.metrics import backend_rate_limit_hits_total

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

# Source label for the Prometheus counter — keeps the cardinality bounded
# while leaving room for future per-source variants (e.g. a Redis-backed
# throttler).
_MIDDLEWARE_SOURCE: str = "api_middleware"


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

    def seconds_until_next_slot(
        self,
        key: str,
        max_requests: int,
        window_seconds: int,
    ) -> int:
        """Return the seconds the caller must wait before the next slot opens.

        Implements the sliding-window UX (T2.4 L2): instead of returning a
        fixed full-window cool-down, we look at the **oldest** request still
        inside the window for ``key`` and compute when it will fall out.
        Once that timestamp expires the caller has at least one slot back.

        Returns ``window_seconds`` as a safe upper bound when the key is
        empty (defensive — should never happen on the rate-limited path)
        and a minimum of ``1`` second so ``Retry-After`` is always
        actionable (RFC 7231 §7.1.3 allows ``0`` but iOS retry logic
        behaves better with a >0 hint).
        """
        timestamps = self._requests.get(key, [])
        if not timestamps:
            return max(1, window_seconds)

        # Sliding window: the next slot opens once the oldest entry within
        # the window ages out (oldest_ts + window_seconds <= now). The
        # number of seconds until that happens is the cool-down hint.
        # When more than max_requests entries are present (shouldn't happen
        # — we cap on push — guard anyway), align on the (max_requests-th)
        # oldest entry so we wait until enough headroom returns.
        sorted_ts = sorted(timestamps)
        anchor = sorted_ts[-max_requests] if len(sorted_ts) >= max_requests else sorted_ts[0]

        now = time.monotonic()
        seconds_until_free = (anchor + window_seconds) - now
        return max(1, int(seconds_until_free) + 1)

    def tokens_available(
        self,
        key: str,
        max_requests: int,
        window_seconds: int,
    ) -> int:
        """Snapshot of remaining slots in the current window for ``key``.

        Used by the L3 structured log so SREs can see headroom (or the
        lack thereof) when triaging rate-limit complaints. Does NOT mutate
        state. Returns 0 when the key is over the cap.
        """
        now = time.monotonic()
        cutoff = now - window_seconds
        live = [t for t in self._requests.get(key, []) if t > cutoff]
        remaining = max_requests - len(live)
        return remaining if remaining > 0 else 0


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

        max_requests = settings.rate_limit_requests_per_minute
        window_seconds = 60

        if self._store.is_rate_limited(
            key=rate_limit_key,
            max_requests=max_requests,
            window_seconds=window_seconds,
        ):
            # T2.4 L2: sliding-window Retry-After. The fixed 60s cool-down
            # was misleading whenever the window was already "thawing" —
            # iOS would back off a full minute while the next slot was a
            # few seconds away. We now query the store for the seconds
            # until the oldest entry ages out and surface that.
            retry_after_seconds = self._store.seconds_until_next_slot(
                key=rate_limit_key,
                max_requests=max_requests,
                window_seconds=window_seconds,
            )
            # Snapshot headroom AFTER the throttler decision: by definition
            # this is 0 on the 429 path, but we read through the store so
            # the field stays consistent with the underlying state and
            # future limit changes don't silently drift the log line.
            tokens_available_after = self._store.tokens_available(
                key=rate_limit_key,
                max_requests=max_requests,
                window_seconds=window_seconds,
            )
            endpoint = _classify_endpoint(path)
            # T2.4 L3: structured 429 log so SREs can grep for actionable
            # context (endpoint + ip + cool-down + headroom snapshot)
            # without joining against the request log. ``tokens_consumed``
            # is the cap minus the remaining headroom; for a saturated
            # window this equals max_requests, which is exactly the data
            # operators need when fielding "your throttler is too tight"
            # complaints.
            await logger.awarning(
                "rate_limit_exceeded",
                client_ip=client_ip,
                path=path,
                endpoint=endpoint,
                tokens_consumed=max_requests - tokens_available_after,
                tokens_available_after=tokens_available_after,
                retry_after_seconds=retry_after_seconds,
                window_seconds=window_seconds,
            )
            # T2.4: emit a separate counter for backend-throttler 429s so
            # operators can graph them independently from the upstream
            # ``claude_rate_limit_hits_total`` (different operational
            # signal entirely). Endpoint label is coarse-grained to avoid
            # cardinality explosion from dynamic path params.
            backend_rate_limit_hits_total.labels(
                endpoint=endpoint,
                source=_MIDDLEWARE_SOURCE,
            ).inc()
            # iOS expects a `rate_limit.info`-shaped JSON body so the
            # client decoder doesn't fork between bridge-origin events
            # and backend-origin throttling responses. ``resets_at`` is
            # an integer unix timestamp in seconds, matching
            # ``RateLimitInfoPayload``.
            resets_at = int(time.time()) + retry_after_seconds
            body: dict[str, object] = {
                "detail": "Too many requests. Please try again later.",
                "rate_limit": {
                    "status": "exceeded",
                    "rate_limit_type": "backend_per_ip",
                    "resets_at": resets_at,
                    "retry_after_seconds": retry_after_seconds,
                    "source": _MIDDLEWARE_SOURCE,
                },
            }
            return JSONResponse(
                status_code=429,
                content=body,
                headers={"Retry-After": str(retry_after_seconds)},
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


def _classify_endpoint(path: str) -> str:
    """Reduce a request path to a low-cardinality Prometheus label.

    Returns the first three segments (e.g. ``/api/v1/auth``) so dynamic
    suffixes like ``/login`` or ``/refresh`` collapse together. Anything
    not matching ``/api/v1/...`` falls back to ``"unknown"``.
    """
    parts = [seg for seg in path.split("/") if seg]
    if len(parts) >= 3 and parts[0] == "api" and parts[1].startswith("v"):
        return "/" + "/".join(parts[:3])
    if parts:
        return "/" + parts[0]
    return "unknown"
