"""Proactive notification database repository."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.proactive_notification import ProactiveNotification


class ProactiveNotificationRepository:
    """Repository for proactive notification CRUD operations."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        notification_type: str,
        priority: str,
        title: str,
        body: str,
        source: str,
        source_event: str | None = None,
        deep_link: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> ProactiveNotification:
        """Create a new proactive notification."""
        notification = ProactiveNotification(
            user_id=user_id,
            type=notification_type,
            priority=priority,
            title=title,
            body=body,
            source=source,
            source_event=source_event,
            deep_link=deep_link,
            metadata_json=metadata or {},
        )
        self._session.add(notification)
        await self._session.flush()
        return notification

    async def get_by_id(
        self,
        notification_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> ProactiveNotification | None:
        """Get a notification by ID, scoped to user."""
        stmt = select(ProactiveNotification).where(
            ProactiveNotification.id == notification_id,
            ProactiveNotification.user_id == user_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_user(
        self,
        user_id: uuid.UUID,
        *,
        page: int = 1,
        page_size: int = 20,
        priority: str | None = None,
        is_read: bool | None = None,
        notification_type: str | None = None,
    ) -> tuple[list[ProactiveNotification], int]:
        """List notifications for a user with optional filters.

        Returns a tuple of (notifications, total_count).
        """
        base = select(ProactiveNotification).where(
            ProactiveNotification.user_id == user_id,
        )
        count_base = select(func.count(ProactiveNotification.id)).where(
            ProactiveNotification.user_id == user_id,
        )

        if priority is not None:
            base = base.where(ProactiveNotification.priority == priority)
            count_base = count_base.where(ProactiveNotification.priority == priority)
        if is_read is not None:
            base = base.where(ProactiveNotification.is_read == is_read)
            count_base = count_base.where(ProactiveNotification.is_read == is_read)
        if notification_type is not None:
            base = base.where(ProactiveNotification.type == notification_type)
            count_base = count_base.where(ProactiveNotification.type == notification_type)

        # Total count
        count_result = await self._session.execute(count_base)
        total = count_result.scalar_one()

        # Paginated results
        offset = (page - 1) * page_size
        stmt = (
            base.order_by(ProactiveNotification.created_at.desc()).offset(offset).limit(page_size)
        )
        result = await self._session.execute(stmt)
        notifications = list(result.scalars().all())

        return notifications, total

    async def mark_read(
        self,
        notification_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> ProactiveNotification | None:
        """Mark a single notification as read."""
        notification = await self.get_by_id(notification_id, user_id)
        if notification is None:
            return None
        notification.is_read = True
        notification.read_at = datetime.now(tz=UTC)
        await self._session.flush()
        return notification

    async def mark_all_read(self, user_id: uuid.UUID) -> int:
        """Mark all unread notifications as read for a user.

        Returns the number of notifications marked.
        """
        now = datetime.now(tz=UTC)
        stmt = (
            update(ProactiveNotification)
            .where(
                ProactiveNotification.user_id == user_id,
                ProactiveNotification.is_read.is_(False),
            )
            .values(is_read=True, read_at=now)
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.rowcount  # type: ignore[attr-defined, no-any-return]

    async def delete_notification(
        self,
        notification_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> bool:
        """Delete a notification. Returns True if deleted."""
        stmt = delete(ProactiveNotification).where(
            ProactiveNotification.id == notification_id,
            ProactiveNotification.user_id == user_id,
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.rowcount > 0  # type: ignore[attr-defined, no-any-return]

    async def unread_count(self, user_id: uuid.UUID) -> int:
        """Return unread notification count for a user."""
        stmt = select(func.count(ProactiveNotification.id)).where(
            ProactiveNotification.user_id == user_id,
            ProactiveNotification.is_read.is_(False),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def exists_by_source_event(
        self,
        user_id: uuid.UUID,
        source_event: str,
    ) -> bool:
        """Check if a notification with the given source_event already exists (dedup)."""
        stmt = select(func.count(ProactiveNotification.id)).where(
            ProactiveNotification.user_id == user_id,
            ProactiveNotification.source_event == source_event,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one() > 0
