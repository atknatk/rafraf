"""Unit tests for ProactiveNotificationService."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.schemas.proactive_notification import (
    CreateProactiveNotification,
    NotificationPriority,
    ProactiveNotificationType,
)
from app.services.proactive_notification_service import ProactiveNotificationService


class TestMapGithubEventType:
    """Tests for _map_github_event_type static method."""

    def test_pr_merged(self) -> None:
        """PR merged event should map to pr_merged type."""
        result = ProactiveNotificationService._map_github_event_type(
            "pull_request", "merged"
        )
        assert result == ProactiveNotificationType.pr_merged

    def test_pr_closed(self) -> None:
        """PR closed event should map to task_complete type."""
        result = ProactiveNotificationService._map_github_event_type(
            "pull_request", "closed"
        )
        assert result == ProactiveNotificationType.task_complete

    def test_issue_opened(self) -> None:
        """Issue opened event should map to issue_detected type."""
        result = ProactiveNotificationService._map_github_event_type(
            "issues", "opened"
        )
        assert result == ProactiveNotificationType.issue_detected

    def test_workflow_failure(self) -> None:
        """Workflow failure should map to ci_failure type."""
        result = ProactiveNotificationService._map_github_event_type(
            "workflow_run", "failure"
        )
        assert result == ProactiveNotificationType.ci_failure

    def test_push_event(self) -> None:
        """Push event should map to task_complete type."""
        result = ProactiveNotificationService._map_github_event_type(
            "push", "push"
        )
        assert result == ProactiveNotificationType.task_complete

    def test_unknown_event(self) -> None:
        """Unknown event should default to issue_detected."""
        result = ProactiveNotificationService._map_github_event_type(
            "unknown", "unknown"
        )
        assert result == ProactiveNotificationType.issue_detected


class TestCreateNotificationDedup:
    """Tests for dedup mechanism in create_notification."""

    @pytest.mark.asyncio
    async def test_dedup_prevents_duplicate(self) -> None:
        """Should skip creation when source_event already exists."""
        mock_session = AsyncMock()
        service = ProactiveNotificationService(mock_session)

        # Mock repo
        with patch.object(service, "_repo") as mock_repo:
            mock_repo.exists_by_source_event = AsyncMock(return_value=True)
            # Return a fake notification for the "existing" check
            mock_notification = MagicMock()
            mock_notification.id = uuid4()
            mock_notification.type = "pr_merged"
            mock_notification.priority = "normal"
            mock_notification.title = "Existing"
            mock_notification.body = "Existing body"
            mock_notification.source = "github"
            mock_notification.source_event = "github:pr:1"
            mock_notification.deep_link = None
            mock_notification.metadata_json = {}
            mock_notification.is_read = False
            mock_notification.read_at = None
            mock_notification.created_at = MagicMock()

            mock_repo.list_for_user = AsyncMock(
                return_value=([mock_notification], 1)
            )

            payload = CreateProactiveNotification(
                user_id=uuid4(),
                type=ProactiveNotificationType.pr_merged,
                title="PR merged",
                body="Test",
                source="github",
                source_event="github:pr:1",
            )

            result = await service.create_notification(payload)
            # Should not call create
            mock_repo.create.assert_not_called()
            assert result.title == "Existing"

    @pytest.mark.asyncio
    async def test_no_dedup_without_source_event(self) -> None:
        """Should create normally when source_event is None."""
        mock_session = AsyncMock()
        service = ProactiveNotificationService(mock_session)

        with patch.object(service, "_repo") as mock_repo:
            mock_notification = MagicMock()
            mock_notification.id = uuid4()
            mock_notification.type = "suggestion"
            mock_notification.priority = "low"
            mock_notification.title = "New"
            mock_notification.body = "New body"
            mock_notification.source = "system"
            mock_notification.source_event = None
            mock_notification.deep_link = None
            mock_notification.metadata_json = {}
            mock_notification.is_read = False
            mock_notification.read_at = None
            mock_notification.created_at = MagicMock()

            mock_repo.create = AsyncMock(return_value=mock_notification)

            payload = CreateProactiveNotification(
                user_id=uuid4(),
                type=ProactiveNotificationType.suggestion,
                priority=NotificationPriority.low,
                title="New",
                body="New body",
                source="system",
            )

            result = await service.create_notification(payload)
            mock_repo.create.assert_called_once()
            assert result.title == "New"


class TestMarkRead:
    """Tests for mark_read and mark_all_read."""

    @pytest.mark.asyncio
    async def test_mark_read_not_found(self) -> None:
        """Should return None when notification not found."""
        mock_session = AsyncMock()
        service = ProactiveNotificationService(mock_session)

        with patch.object(service, "_repo") as mock_repo:
            mock_repo.mark_read = AsyncMock(return_value=None)

            result = await service.mark_read(uuid4(), uuid4())
            assert result is None

    @pytest.mark.asyncio
    async def test_mark_all_read(self) -> None:
        """Should return marked_count."""
        mock_session = AsyncMock()
        service = ProactiveNotificationService(mock_session)

        with patch.object(service, "_repo") as mock_repo:
            mock_repo.mark_all_read = AsyncMock(return_value=5)

            result = await service.mark_all_read(uuid4())
            assert result.marked_count == 5


class TestGetUnreadCount:
    """Tests for get_unread_count."""

    @pytest.mark.asyncio
    async def test_unread_count(self) -> None:
        """Should return correct unread count."""
        mock_session = AsyncMock()
        service = ProactiveNotificationService(mock_session)

        with patch.object(service, "_repo") as mock_repo:
            mock_repo.unread_count = AsyncMock(return_value=3)

            result = await service.get_unread_count(uuid4())
            assert result.count == 3

    @pytest.mark.asyncio
    async def test_zero_unread_count(self) -> None:
        """Should return zero when no unread notifications."""
        mock_session = AsyncMock()
        service = ProactiveNotificationService(mock_session)

        with patch.object(service, "_repo") as mock_repo:
            mock_repo.unread_count = AsyncMock(return_value=0)

            result = await service.get_unread_count(uuid4())
            assert result.count == 0
