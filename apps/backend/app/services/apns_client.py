"""APNs client — async Apple Push Notification delivery via aioapns."""

import structlog
from aioapns import APNs, NotificationRequest
from aioapns import ConnectionError as APNsConnectionError

from app.core.config import get_settings

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

# Module-level lazy singleton
_apns_client: APNs | None = None
_init_attempted: bool = False


def _get_apns() -> APNs | None:
    """Lazy-initialize the APNs client. Returns None if not configured."""
    global _apns_client, _init_attempted  # noqa: PLW0603

    if _init_attempted:
        return _apns_client

    _init_attempted = True
    settings = get_settings()

    if not settings.apns_key_path or not settings.apns_key_id or not settings.apns_team_id:
        logger.warning(
            "apns_not_configured",
            reason="Missing apns_key_path, apns_key_id, or apns_team_id",
        )
        return None

    try:
        _apns_client = APNs(
            key=settings.apns_key_path,
            key_id=settings.apns_key_id,
            team_id=settings.apns_team_id,
            topic=settings.apns_bundle_id,
            use_sandbox=settings.apns_use_sandbox,
        )
    except Exception:
        logger.exception("apns_init_failed")

    return _apns_client


async def send_push(
    *,
    token: str,
    title: str,
    body: str,
    data: dict[str, object] | None = None,
    badge: int | None = None,
    sound: str = "default",
    category: str | None = None,
) -> bool:
    """Send a single push notification via APNs.

    Returns True if delivery was accepted, False otherwise.
    """
    client = _get_apns()
    if client is None:
        await logger.awarning("apns_send_skipped_not_configured")
        return False

    alert: dict[str, str] = {"title": title, "body": body}
    aps: dict[str, object] = {"alert": alert, "sound": sound}
    if badge is not None:
        aps["badge"] = badge
    if category is not None:
        aps["category"] = category

    payload: dict[str, object] = {"aps": aps}
    if data:
        payload.update(data)

    request = NotificationRequest(
        device_token=token,
        message=payload,
    )

    try:
        response = await client.send_notification(request)
        if not response.is_successful:
            await logger.awarning(
                "apns_send_failed",
                token_prefix=token[:8],
                reason=response.description,
            )
            return False
        return True
    except APNsConnectionError:
        await logger.aexception("apns_connection_error", token_prefix=token[:8])
        return False
    except Exception:
        await logger.aexception("apns_send_error", token_prefix=token[:8])
        return False


def is_token_invalid_reason(reason: str | None) -> bool:
    """Check if an APNs error reason indicates an invalid token."""
    invalid_reasons = {"BadDeviceToken", "Unregistered", "DeviceTokenNotForTopic"}
    return reason in invalid_reasons if reason else False
