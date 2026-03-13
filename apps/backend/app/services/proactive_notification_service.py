"""Proactive notification service — creation, delivery, and management."""

import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.proactive_notification import (
    ProactiveNotification as ProactiveNotificationModel,
)
from app.repositories.proactive_notification_repo import (
    ProactiveNotificationRepository,
)
from app.schemas.notifications import NotificationPayload, NotificationType
from app.schemas.proactive_notification import (
    CreateProactiveNotification,
    MarkAllReadResponse,
    NotificationPriority,
    ProactiveNotificationListResponse,
    ProactiveNotificationResponse,
    ProactiveNotificationType,
    UnreadCountResponse,
)

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

# GitHub event -> proactive notification mapping
_GITHUB_EVENT_PRIORITY: dict[str, NotificationPriority] = {
    "ci_failure": NotificationPriority.urgent,
    "pr_merged": NotificationPriority.normal,
    "issue_opened": NotificationPriority.normal,
    "security_alert": NotificationPriority.urgent,
}


def _model_to_response(
    notification: ProactiveNotificationModel,
) -> ProactiveNotificationResponse:
    """Convert a SQLAlchemy ProactiveNotification to response schema."""
    return ProactiveNotificationResponse(
        id=notification.id,
        type=ProactiveNotificationType(notification.type),
        priority=NotificationPriority(notification.priority),
        title=notification.title,
        body=notification.body,
        source=notification.source,
        source_event=notification.source_event,
        deep_link=notification.deep_link,
        metadata=notification.metadata_json,
        is_read=notification.is_read,
        read_at=notification.read_at,
        created_at=notification.created_at,
    )


class ProactiveNotificationService:
    """Orchestrates proactive notification lifecycle."""

    def __init__(self, session: AsyncSession) -> None:
        self._repo = ProactiveNotificationRepository(session)
        self._session = session

    # ------------------------------------------------------------------
    # Creation
    # ------------------------------------------------------------------

    async def create_notification(
        self,
        payload: CreateProactiveNotification,
    ) -> ProactiveNotificationResponse:
        """Create a proactive notification.

        Applies dedup: if source_event is set and already exists, returns None-ish.
        Sends push for urgent notifications.
        """
        # Dedup check
        if payload.source_event:
            exists = await self._repo.exists_by_source_event(
                user_id=payload.user_id,
                source_event=payload.source_event,
            )
            if exists:
                await logger.ainfo(
                    "proactive_notification_dedup_skipped",
                    user_id=str(payload.user_id),
                    source_event=payload.source_event,
                )
                # Return a minimal response — caller should handle
                # In practice we still want to return something for the WS push
                # so we fetch the existing one
                notifications, _ = await self._repo.list_for_user(
                    user_id=payload.user_id,
                    page=1,
                    page_size=1,
                )
                if notifications:
                    return _model_to_response(notifications[0])

        notification = await self._repo.create(
            user_id=payload.user_id,
            notification_type=payload.type.value,
            priority=payload.priority.value,
            title=payload.title,
            body=payload.body,
            source=payload.source,
            source_event=payload.source_event,
            deep_link=payload.deep_link,
            metadata=payload.metadata,
        )

        await logger.ainfo(
            "proactive_notification_created",
            notification_id=str(notification.id),
            user_id=str(payload.user_id),
            type=payload.type.value,
            priority=payload.priority.value,
            source=payload.source,
        )

        # Send push notification for urgent priority
        if payload.priority == NotificationPriority.urgent:
            await self._send_push(payload.user_id, notification)

        return _model_to_response(notification)

    async def create_from_github_event(
        self,
        *,
        user_id: uuid.UUID,
        event_type: str,
        action: str,
        repo: str,
        title: str,
        body: str,
        source_event: str,
        deep_link: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> ProactiveNotificationResponse:
        """Create a proactive notification from a GitHub webhook event."""
        # Map GitHub event to notification type
        notification_type = self._map_github_event_type(event_type, action)
        priority = _GITHUB_EVENT_PRIORITY.get(
            notification_type.value,
            NotificationPriority.normal,
        )

        payload = CreateProactiveNotification(
            user_id=user_id,
            type=notification_type,
            priority=priority,
            title=title,
            body=body,
            source="github",
            source_event=source_event,
            deep_link=deep_link,
            metadata=metadata or {"repo": repo, "event": event_type, "action": action},
        )
        return await self.create_notification(payload)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    async def get_notifications(
        self,
        user_id: uuid.UUID,
        *,
        page: int = 1,
        page_size: int = 20,
        priority: str | None = None,
        is_read: bool | None = None,
        notification_type: str | None = None,
    ) -> ProactiveNotificationListResponse:
        """Get paginated list of notifications for a user."""
        notifications, total = await self._repo.list_for_user(
            user_id=user_id,
            page=page,
            page_size=page_size,
            priority=priority,
            is_read=is_read,
            notification_type=notification_type,
        )

        return ProactiveNotificationListResponse(
            notifications=[_model_to_response(n) for n in notifications],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def get_unread_count(self, user_id: uuid.UUID) -> UnreadCountResponse:
        """Get unread notification count."""
        count = await self._repo.unread_count(user_id)
        return UnreadCountResponse(count=count)

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    async def mark_read(
        self,
        notification_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> ProactiveNotificationResponse | None:
        """Mark a notification as read."""
        notification = await self._repo.mark_read(notification_id, user_id)
        if notification is None:
            return None
        await logger.ainfo(
            "proactive_notification_marked_read",
            notification_id=str(notification_id),
            user_id=str(user_id),
        )
        return _model_to_response(notification)

    async def mark_all_read(self, user_id: uuid.UUID) -> MarkAllReadResponse:
        """Mark all notifications as read."""
        count = await self._repo.mark_all_read(user_id)
        await logger.ainfo(
            "proactive_notifications_all_marked_read",
            user_id=str(user_id),
            marked_count=count,
        )
        return MarkAllReadResponse(marked_count=count)

    async def delete_notification(
        self,
        notification_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> bool:
        """Delete a notification. Returns True if deleted."""
        deleted = await self._repo.delete_notification(notification_id, user_id)
        if deleted:
            await logger.ainfo(
                "proactive_notification_deleted",
                notification_id=str(notification_id),
                user_id=str(user_id),
            )
        return deleted

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _map_github_event_type(
        event_type: str,
        action: str,
    ) -> ProactiveNotificationType:
        """Map a GitHub event type + action to a ProactiveNotificationType."""
        if event_type == "pull_request" and action == "merged":
            return ProactiveNotificationType.pr_merged
        if event_type == "pull_request" and action == "closed":
            return ProactiveNotificationType.task_complete
        if event_type == "issues" and action == "opened":
            return ProactiveNotificationType.issue_detected
        if event_type == "workflow_run" and action in ("failure", "completed"):
            return ProactiveNotificationType.ci_failure
        if event_type == "push":
            return ProactiveNotificationType.task_complete
        return ProactiveNotificationType.issue_detected

    async def _send_push(
        self,
        user_id: uuid.UUID,
        notification: ProactiveNotificationModel,
    ) -> None:
        """Send APNs push notification for urgent proactive notifications."""
        try:
            from app.services.notification_service import NotificationService

            push_service = NotificationService(self._session)
            push_payload = NotificationPayload(
                notification_id=notification.id,
                type=NotificationType.info,
                title=notification.title,
                body=notification.body,
                deep_link=notification.deep_link,
                metadata={
                    "proactive_notification_id": str(notification.id),
                    "proactive_type": notification.type,
                },
            )
            await push_service.send_notification(user_id, push_payload)
        except Exception:
            await logger.aexception(
                "proactive_notification_push_failed",
                user_id=str(user_id),
            )
