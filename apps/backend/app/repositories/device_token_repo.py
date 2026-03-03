"""Device token and notification settings database repository."""

import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device_token import DeviceToken, NotificationSettings


class DeviceTokenRepository:
    """Repository for device token CRUD operations."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(
        self,
        user_id: uuid.UUID,
        token: str,
        platform: str = "ios",
        app_version: str | None = None,
    ) -> DeviceToken:
        """Insert or update a device token (reactivate if deactivated)."""
        # Check if token already exists for this user
        existing_stmt = select(DeviceToken).where(
            DeviceToken.user_id == user_id,
            DeviceToken.token == token,
        )
        existing_result = await self._session.execute(existing_stmt)
        existing = existing_result.scalar_one_or_none()

        if existing is not None:
            existing.is_active = True
            existing.app_version = app_version
            await self._session.flush()
            return existing

        device_token = DeviceToken(
            user_id=user_id,
            token=token,
            platform=platform,
            app_version=app_version,
            is_active=True,
        )
        self._session.add(device_token)
        await self._session.flush()
        return device_token

    async def deactivate(self, user_id: uuid.UUID, token: str) -> None:
        """Mark a device token as inactive (soft delete)."""
        stmt = (
            update(DeviceToken)
            .where(
                DeviceToken.user_id == user_id,
                DeviceToken.token == token,
            )
            .values(is_active=False)
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def get_active_tokens(self, user_id: uuid.UUID) -> list[DeviceToken]:
        """Return all active device tokens for a user."""
        stmt = select(DeviceToken).where(
            DeviceToken.user_id == user_id,
            DeviceToken.is_active.is_(True),
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class NotificationSettingsRepository:
    """Repository for per-user notification settings."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create(self, user_id: uuid.UUID) -> NotificationSettings:
        """Return existing settings or create defaults."""
        stmt = select(NotificationSettings).where(
            NotificationSettings.user_id == user_id,
        )
        result = await self._session.execute(stmt)
        settings = result.scalar_one_or_none()
        if settings is not None:
            return settings

        settings = NotificationSettings(user_id=user_id)
        self._session.add(settings)
        await self._session.flush()
        return settings

    async def update_settings(
        self,
        user_id: uuid.UUID,
        *,
        task_complete_enabled: bool | None = None,
        approval_needed_enabled: bool | None = None,
        error_enabled: bool | None = None,
        info_enabled: bool | None = None,
    ) -> NotificationSettings:
        """Partially update notification settings; create if missing."""
        settings = await self.get_or_create(user_id)
        if task_complete_enabled is not None:
            settings.task_complete_enabled = task_complete_enabled
        if approval_needed_enabled is not None:
            settings.approval_needed_enabled = approval_needed_enabled
        if error_enabled is not None:
            settings.error_enabled = error_enabled
        if info_enabled is not None:
            settings.info_enabled = info_enabled
        await self._session.flush()
        return settings
