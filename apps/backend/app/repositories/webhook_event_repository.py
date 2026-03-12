"""Webhook event repository — async database access layer."""

import uuid
from collections.abc import Sequence

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.webhook_event import WebhookEvent

logger: structlog.stdlib.BoundLogger = structlog.get_logger()


class WebhookEventRepository:
    """DB access layer for webhook_events table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_by_delivery_id(self, delivery_id: str) -> WebhookEvent | None:
        """Find an event by its GitHub delivery ID.

        Args:
            delivery_id: GitHub X-GitHub-Delivery header value.

        Returns:
            WebhookEvent if found, None otherwise.
        """
        query = select(WebhookEvent).where(
            WebhookEvent.delivery_id == delivery_id,
        )
        result = await self._session.execute(query)
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        delivery_id: str,
        event_type: str,
        action: str,
        repo: str,
        sender: str,
        summary: dict[str, object],
        processed: bool = False,
    ) -> WebhookEvent:
        """Create a new webhook event record.

        Args:
            delivery_id: GitHub delivery ID.
            event_type: Event type (push, pull_request, issues, check_run).
            action: Event action.
            repo: Repository full name.
            sender: Sender login.
            summary: Event summary data.
            processed: Whether the event has been processed.

        Returns:
            Created WebhookEvent.
        """
        record = WebhookEvent(
            delivery_id=delivery_id,
            event_type=event_type,
            action=action,
            repo=repo,
            sender=sender,
            summary=summary,
            processed=processed,
        )
        self._session.add(record)
        await self._session.flush()
        await logger.adebug(
            "webhook_event_created",
            delivery_id=delivery_id,
            event_type=event_type,
        )
        return record

    async def mark_processed(self, event_id: uuid.UUID) -> None:
        """Mark a webhook event as processed.

        Args:
            event_id: Event UUID.
        """
        query = select(WebhookEvent).where(WebhookEvent.id == event_id)
        result = await self._session.execute(query)
        event = result.scalar_one_or_none()
        if event is not None:
            event.processed = True
            await self._session.flush()

    async def list_recent(
        self,
        *,
        limit: int = 20,
        event_type: str | None = None,
    ) -> Sequence[WebhookEvent]:
        """List recent webhook events, optionally filtered by type.

        Args:
            limit: Maximum number of events to return.
            event_type: Optional filter by event type.

        Returns:
            Sequence of WebhookEvent records.
        """
        query = select(WebhookEvent).order_by(
            WebhookEvent.created_at.desc(),
        )
        if event_type is not None:
            query = query.where(WebhookEvent.event_type == event_type)
        query = query.limit(min(limit, 100))
        result = await self._session.execute(query)
        return result.scalars().all()

    async def count(self, *, event_type: str | None = None) -> int:
        """Count webhook events, optionally filtered by type.

        Args:
            event_type: Optional filter by event type.

        Returns:
            Total count.
        """
        query = select(func.count()).select_from(WebhookEvent)
        if event_type is not None:
            query = query.where(WebhookEvent.event_type == event_type)
        result = await self._session.execute(query)
        return result.scalar_one()
