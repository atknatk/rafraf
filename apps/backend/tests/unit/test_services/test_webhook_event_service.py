"""Unit tests for WebhookEventService."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.webhook_event_service import WebhookEventService


class TestIsDuplicate:
    """Tests for WebhookEventService.is_duplicate."""

    @pytest.mark.asyncio
    async def test_returns_true_when_event_exists(self) -> None:
        """is_duplicate returns True when delivery_id already in DB."""
        session = AsyncMock()
        service = WebhookEventService(session)

        existing_event = MagicMock()
        with patch.object(
            service._repo,
            "find_by_delivery_id",
            new_callable=AsyncMock,
            return_value=existing_event,
        ):
            result = await service.is_duplicate("delivery-123")
            assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_event_not_exists(self) -> None:
        """is_duplicate returns False when delivery_id is new."""
        session = AsyncMock()
        service = WebhookEventService(session)

        with patch.object(
            service._repo,
            "find_by_delivery_id",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await service.is_duplicate("new-delivery-456")
            assert result is False


class TestRecordEvent:
    """Tests for WebhookEventService.record_event."""

    @pytest.mark.asyncio
    async def test_record_event_creates_db_entry(self) -> None:
        """record_event should delegate to repository create."""
        session = AsyncMock()
        service = WebhookEventService(session)

        mock_event = MagicMock()
        mock_event.id = uuid4()
        mock_event.delivery_id = "delivery-789"

        with patch.object(
            service._repo,
            "create",
            new_callable=AsyncMock,
            return_value=mock_event,
        ) as mock_create:
            result = await service.record_event(
                delivery_id="delivery-789",
                event_type="push",
                action="push",
                repo="owner/repo",
                sender="user1",
                summary={"branch": "main"},
            )
            assert result == mock_event
            mock_create.assert_awaited_once_with(
                delivery_id="delivery-789",
                event_type="push",
                action="push",
                repo="owner/repo",
                sender="user1",
                summary={"branch": "main"},
                processed=True,
            )


class TestListEvents:
    """Tests for WebhookEventService.list_events."""

    @pytest.mark.asyncio
    async def test_list_events_returns_events_and_count(self) -> None:
        """list_events returns tuple of events and total count."""
        session = AsyncMock()
        service = WebhookEventService(session)

        mock_events = [MagicMock(), MagicMock()]

        with (
            patch.object(
                service._repo,
                "list_recent",
                new_callable=AsyncMock,
                return_value=mock_events,
            ),
            patch.object(
                service._repo,
                "count",
                new_callable=AsyncMock,
                return_value=5,
            ),
        ):
            events, total = await service.list_events(limit=20)
            assert len(events) == 2
            assert total == 5

    @pytest.mark.asyncio
    async def test_list_events_passes_event_type_filter(self) -> None:
        """list_events passes event_type filter to repository."""
        session = AsyncMock()
        service = WebhookEventService(session)

        with (
            patch.object(
                service._repo,
                "list_recent",
                new_callable=AsyncMock,
                return_value=[],
            ) as mock_list,
            patch.object(
                service._repo,
                "count",
                new_callable=AsyncMock,
                return_value=0,
            ) as mock_count,
        ):
            await service.list_events(limit=10, event_type="check_run")
            mock_list.assert_awaited_once_with(limit=10, event_type="check_run")
            mock_count.assert_awaited_once_with(event_type="check_run")
