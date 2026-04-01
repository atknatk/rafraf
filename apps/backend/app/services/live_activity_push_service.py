"""Live Activity push service — sends APNs pushes for iOS Live Activity updates."""

import time

import structlog

from app.core.config import get_settings

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

# Default throttle interval in seconds
_THROTTLE_INTERVAL_SECONDS: int = 30


class APNsGoneError(Exception):
    """Raised when APNs returns 410 Gone for an invalidated push token."""

    def __init__(self, token: str) -> None:
        self.token = token
        super().__init__(f"APNs 410 Gone: token {token[:8]}... is invalid")


class LiveActivityPushService:
    """Manages APNs push notifications for iOS Live Activity updates.

    Features:
    - Monotonically increasing timestamps per push token
    - Rate limiting (throttle): max 1 push per 30 seconds per token
    - Invalid token tracking (410 Gone -> skip future pushes)
    - APNs payload builder for Live Activity update/end events
    """

    def __init__(self, bundle_id: str | None = None) -> None:
        settings = get_settings()
        self._bundle_id: str = bundle_id or settings.apns_bundle_id
        # Per-token last push timestamp for throttling
        self._last_push_time: dict[str, float] = {}
        # Per-token monotonic timestamp counter
        self._last_timestamp: dict[str, int] = {}
        # Set of tokens marked as invalid (410 Gone)
        self._invalid_tokens: set[str] = set()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def send_live_activity_update(
        self,
        push_token: str,
        content_state: dict[str, object],
        event: str = "update",
        stale_minutes: int = 15,
    ) -> bool:
        """Send a Live Activity update push notification.

        Returns True if the push was sent successfully, False otherwise.
        """
        if self._should_skip_token(push_token):
            return False

        if self._should_throttle(push_token):
            return False

        payload = self._build_payload(
            content_state=content_state,
            event=event,
            stale_minutes=stale_minutes,
        )
        headers = self._build_headers()

        try:
            result = await self._send_notification(
                push_token=push_token,
                payload=payload,
                headers=headers,
            )
            self._last_push_time[push_token] = time.time()
            return bool(result)
        except Exception as exc:
            error_msg = str(exc)
            if "410" in error_msg:
                self._invalid_tokens.add(push_token)
                await logger.awarning(
                    "apns_token_invalidated",
                    token_prefix=push_token[:8],
                )
            else:
                await logger.aexception(
                    "live_activity_push_error",
                    token_prefix=push_token[:8],
                )
            return False

    async def send_live_activity_end(
        self,
        push_token: str,
        content_state: dict[str, object],
        dismissal_hours: int = 4,
    ) -> bool:
        """Send a Live Activity end push notification.

        Returns True if the push was sent successfully, False otherwise.
        """
        if self._should_skip_token(push_token):
            return False

        payload = self._build_payload(
            content_state=content_state,
            event="end",
            dismissal_hours=dismissal_hours,
        )
        headers = self._build_headers()

        try:
            result = await self._send_notification(
                push_token=push_token,
                payload=payload,
                headers=headers,
            )
            return bool(result)
        except Exception as exc:
            error_msg = str(exc)
            if "410" in error_msg:
                self._invalid_tokens.add(push_token)
            await logger.aexception(
                "live_activity_end_push_error",
                token_prefix=push_token[:8],
            )
            return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _should_throttle(self, push_token: str) -> bool:
        """Check if push should be throttled (max 1 per 30s per token)."""
        last_time = self._last_push_time.get(push_token)
        if last_time is None:
            return False
        elapsed = time.time() - last_time
        return elapsed < _THROTTLE_INTERVAL_SECONDS

    def _should_skip_token(self, push_token: str) -> bool:
        """Check if token has been marked as invalid (410 Gone)."""
        return push_token in self._invalid_tokens

    def _build_payload(
        self,
        content_state: dict[str, object],
        event: str = "update",
        stale_minutes: int = 15,
        dismissal_hours: int | None = None,
    ) -> dict[str, object]:
        """Build the APNs payload for a Live Activity push.

        Returns a dict matching Apple's Live Activity payload format.
        """
        now = int(time.time())

        # Ensure monotonically increasing timestamps
        # Use a global counter since we don't have per-token context here
        # The caller tracks per-token via _last_timestamp
        timestamp = now
        # Check all tokens' last timestamps to ensure monotonicity
        max_prev = max(self._last_timestamp.values(), default=0)
        if timestamp <= max_prev:
            timestamp = max_prev + 1
        # Store for future monotonicity checks
        self._last_timestamp["_global"] = timestamp

        aps: dict[str, object] = {
            "timestamp": timestamp,
            "event": event,
            "content-state": dict(content_state),
        }

        if event == "end" and dismissal_hours is not None:
            aps["dismissal-date"] = now + (dismissal_hours * 3600)

        payload: dict[str, object] = {"aps": aps}

        # stale-date goes at top level, NOT inside aps
        if event != "end":
            payload["stale-date"] = now + (stale_minutes * 60)

        return payload

    def _build_headers(self) -> dict[str, str]:
        """Build APNs headers for Live Activity push."""
        return {
            "apns-push-type": "liveactivity",
            "apns-topic": f"{self._bundle_id}.push-type.liveactivity",
            "apns-priority": "10",
        }

    async def _send_notification(
        self,
        push_token: str,
        payload: dict[str, object],
        headers: dict[str, str],
    ) -> bool:
        """Send the actual APNs notification. Meant to be overridden/mocked in tests.

        In production, this delegates to the APNs client.
        """
        from app.services.apns_client import _get_apns

        client = _get_apns()
        if client is None:
            await logger.awarning("apns_live_activity_skipped_not_configured")
            return False

        from aioapns import NotificationRequest

        request = NotificationRequest(
            device_token=push_token,
            message=payload,
            headers=headers,
        )

        response = await client.send_notification(request)
        if not response.is_successful:
            if response.description and "410" in str(response.description):
                raise Exception("410 Gone")  # noqa: TRY002
            await logger.awarning(
                "live_activity_push_failed",
                token_prefix=push_token[:8],
                reason=response.description,
            )
            return False
        return True
