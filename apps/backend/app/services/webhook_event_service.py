"""Webhook event service — business logic for GitHub webhook processing."""

from collections.abc import Sequence

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.webhook_event import WebhookEvent
from app.repositories.webhook_event_repository import WebhookEventRepository

logger: structlog.stdlib.BoundLogger = structlog.get_logger()


class WebhookEventService:
    """Handles webhook event persistence, idempotency checks, and listing."""

    def __init__(self, session: AsyncSession) -> None:
        self._repo = WebhookEventRepository(session)

    async def is_duplicate(self, delivery_id: str) -> bool:
        """Check if a webhook event has already been received.

        Args:
            delivery_id: GitHub X-GitHub-Delivery header value.

        Returns:
            True if the event already exists in the database.
        """
        existing = await self._repo.find_by_delivery_id(delivery_id)
        return existing is not None

    async def record_event(
        self,
        *,
        delivery_id: str,
        event_type: str,
        action: str,
        repo: str,
        sender: str,
        summary: dict[str, object],
    ) -> WebhookEvent:
        """Record a new webhook event in the database.

        Args:
            delivery_id: GitHub delivery ID.
            event_type: Event type.
            action: Event action.
            repo: Repository full name.
            sender: Sender login.
            summary: Event summary dict.

        Returns:
            Created WebhookEvent record.
        """
        event = await self._repo.create(
            delivery_id=delivery_id,
            event_type=event_type,
            action=action,
            repo=repo,
            sender=sender,
            summary=summary,
            processed=True,
        )
        await logger.ainfo(
            "webhook_event_recorded",
            delivery_id=delivery_id,
            event_type=event_type,
            action=action,
            repo=repo,
        )
        return event

    async def list_events(
        self,
        *,
        limit: int = 20,
        event_type: str | None = None,
    ) -> tuple[Sequence[WebhookEvent], int]:
        """List recent webhook events with total count.

        Args:
            limit: Maximum number of events.
            event_type: Optional event type filter.

        Returns:
            Tuple of (events, total_count).
        """
        events = await self._repo.list_recent(
            limit=limit,
            event_type=event_type,
        )
        total = await self._repo.count(event_type=event_type)
        return events, total
