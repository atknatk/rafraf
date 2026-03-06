"""Push notification service — token management and notification dispatch."""

import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.device_token_repo import (
    DeviceTokenRepository,
    NotificationSettingsRepository,
)
from app.schemas.notifications import (
    DeviceTokenRegisterResponse,
    NotificationPayload,
    NotificationSettingsResponse,
    NotificationSettingsUpdateRequest,
    NotificationType,
)

logger: structlog.stdlib.BoundLogger = structlog.get_logger()


class NotificationService:
    """Orchestrates device-token CRUD, settings, and push delivery."""

    def __init__(self, session: AsyncSession) -> None:
        self._token_repo = DeviceTokenRepository(session)
        self._settings_repo = NotificationSettingsRepository(session)

    # ------------------------------------------------------------------
    # Device token management
    # ------------------------------------------------------------------

    async def register_token(
        self,
        user_id: uuid.UUID,
        token: str,
        platform: str = "ios",
        app_version: str | None = None,
    ) -> DeviceTokenRegisterResponse:
        """Register (upsert) a device token for push notifications."""
        device_token = await self._token_repo.upsert(
            user_id=user_id,
            token=token,
            platform=platform,
            app_version=app_version,
        )
        await logger.ainfo(
            "device_token_registered",
            user_id=str(user_id),
            platform=platform,
        )
        return DeviceTokenRegisterResponse(
            id=device_token.id,
            registered_at=device_token.created_at,
        )

    async def deactivate_token(
        self,
        user_id: uuid.UUID,
        token: str,
    ) -> None:
        """Soft-delete a device token (e.g. on logout)."""
        await self._token_repo.deactivate(user_id=user_id, token=token)
        await logger.ainfo(
            "device_token_deactivated",
            user_id=str(user_id),
        )

    # ------------------------------------------------------------------
    # Notification settings
    # ------------------------------------------------------------------

    async def get_settings(
        self,
        user_id: uuid.UUID,
    ) -> NotificationSettingsResponse:
        """Return current notification preferences for a user."""
        settings = await self._settings_repo.get_or_create(user_id)
        return NotificationSettingsResponse(
            task_complete_enabled=settings.task_complete_enabled,
            approval_needed_enabled=settings.approval_needed_enabled,
            error_enabled=settings.error_enabled,
            info_enabled=settings.info_enabled,
        )

    async def update_settings(
        self,
        user_id: uuid.UUID,
        payload: NotificationSettingsUpdateRequest,
    ) -> NotificationSettingsResponse:
        """Partially update notification preferences."""
        settings = await self._settings_repo.update_settings(
            user_id=user_id,
            task_complete_enabled=payload.task_complete_enabled,
            approval_needed_enabled=payload.approval_needed_enabled,
            error_enabled=payload.error_enabled,
            info_enabled=payload.info_enabled,
        )
        await logger.ainfo(
            "notification_settings_updated",
            user_id=str(user_id),
        )
        return NotificationSettingsResponse(
            task_complete_enabled=settings.task_complete_enabled,
            approval_needed_enabled=settings.approval_needed_enabled,
            error_enabled=settings.error_enabled,
            info_enabled=settings.info_enabled,
        )

    # ------------------------------------------------------------------
    # Notification dispatch
    # ------------------------------------------------------------------

    async def send_notification(
        self,
        user_id: uuid.UUID,
        notification: NotificationPayload,
    ) -> bool:
        """Send a push notification to all active devices of a user.

        Checks user's category preferences before sending.
        Returns True if at least one device received the notification.
        """
        # Check user preferences
        settings = await self._settings_repo.get_or_create(user_id)
        if not self._is_category_enabled(settings, notification.type):
            await logger.ainfo(
                "notification_skipped_disabled_category",
                user_id=str(user_id),
                notification_type=notification.type.value,
            )
            return False

        tokens = await self._token_repo.get_active_tokens(user_id)
        if not tokens:
            await logger.ainfo(
                "notification_skipped_no_tokens",
                user_id=str(user_id),
            )
            return False

        from app.services.apns_client import send_push

        sent_count = 0
        for device_token in tokens:
            success = await send_push(
                token=device_token.token,
                title=notification.title,
                body=notification.body,
                data=dict(notification.metadata) if notification.metadata else None,
                badge=notification.badge_count or None,
                category=notification.type.value,
            )
            if success:
                sent_count += 1
                await logger.ainfo(
                    "notification_dispatched",
                    user_id=str(user_id),
                    notification_type=notification.type.value,
                    token_prefix=device_token.token[:8],
                )
            else:
                # Deactivate invalid tokens
                await self._token_repo.deactivate(
                    user_id=user_id,
                    token=device_token.token,
                )
                await logger.awarning(
                    "notification_token_deactivated",
                    user_id=str(user_id),
                    token_prefix=device_token.token[:8],
                )

        return sent_count > 0

    @staticmethod
    def _is_category_enabled(
        settings: object,
        notification_type: NotificationType,
    ) -> bool:
        """Check whether a notification category is enabled."""
        mapping: dict[NotificationType, str] = {
            NotificationType.task_complete: "task_complete_enabled",
            NotificationType.approval_needed: "approval_needed_enabled",
            NotificationType.error: "error_enabled",
            NotificationType.info: "info_enabled",
        }
        attr = mapping.get(notification_type, "info_enabled")
        return bool(getattr(settings, attr, True))
