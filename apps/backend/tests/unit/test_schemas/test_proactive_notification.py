"""Unit tests for proactive notification Pydantic schemas."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.proactive_notification import (
    CreateProactiveNotification,
    MarkAllReadResponse,
    NotificationPriority,
    ProactiveNotificationListResponse,
    ProactiveNotificationResponse,
    ProactiveNotificationType,
    UnreadCountResponse,
)


class TestProactiveNotificationType:
    """Tests for ProactiveNotificationType enum."""

    def test_all_types_exist(self) -> None:
        """Should have exactly 7 proactive notification types."""
        assert len(ProactiveNotificationType) == 7
        assert ProactiveNotificationType.task_complete.value == "task_complete"
        assert ProactiveNotificationType.issue_detected.value == "issue_detected"
        assert ProactiveNotificationType.suggestion.value == "suggestion"
        assert ProactiveNotificationType.reminder.value == "reminder"
        assert ProactiveNotificationType.ci_failure.value == "ci_failure"
        assert ProactiveNotificationType.pr_merged.value == "pr_merged"
        assert ProactiveNotificationType.security_alert.value == "security_alert"


class TestNotificationPriority:
    """Tests for NotificationPriority enum."""

    def test_all_priorities_exist(self) -> None:
        """Should have exactly 3 priority levels."""
        assert len(NotificationPriority) == 3
        assert NotificationPriority.urgent.value == "urgent"
        assert NotificationPriority.normal.value == "normal"
        assert NotificationPriority.low.value == "low"


class TestProactiveNotificationResponse:
    """Tests for ProactiveNotificationResponse schema."""

    def test_valid_response(self) -> None:
        """Should accept valid notification response."""
        uid = uuid4()
        now = datetime.now(tz=UTC)
        resp = ProactiveNotificationResponse(
            id=uid,
            type=ProactiveNotificationType.pr_merged,
            priority=NotificationPriority.normal,
            title="PR #42 merged",
            body="feat(backend): auth eklendi",
            source="github",
            is_read=False,
            created_at=now,
        )
        assert resp.id == uid
        assert resp.type == ProactiveNotificationType.pr_merged
        assert resp.priority == NotificationPriority.normal
        assert resp.source_event is None
        assert resp.deep_link is None
        assert resp.metadata == {}
        assert resp.read_at is None

    def test_response_with_optional_fields(self) -> None:
        """Should accept all optional fields."""
        uid = uuid4()
        now = datetime.now(tz=UTC)
        resp = ProactiveNotificationResponse(
            id=uid,
            type=ProactiveNotificationType.ci_failure,
            priority=NotificationPriority.urgent,
            title="CI Failed",
            body="Pipeline failed",
            source="github",
            source_event="github:workflow:repo:123:failure",
            deep_link="https://github.com/repo/actions",
            metadata={"repo": "atknatk/rafraf"},
            is_read=True,
            read_at=now,
            created_at=now,
        )
        assert resp.source_event == "github:workflow:repo:123:failure"
        assert resp.deep_link == "https://github.com/repo/actions"
        assert resp.metadata == {"repo": "atknatk/rafraf"}
        assert resp.is_read is True
        assert resp.read_at == now

    def test_response_is_frozen(self) -> None:
        """Should be immutable (frozen)."""
        uid = uuid4()
        now = datetime.now(tz=UTC)
        resp = ProactiveNotificationResponse(
            id=uid,
            type=ProactiveNotificationType.suggestion,
            priority=NotificationPriority.low,
            title="Oneri",
            body="Test oneri",
            source="system",
            is_read=False,
            created_at=now,
        )
        with pytest.raises(ValidationError):
            resp.title = "Changed"  # type: ignore[misc]


class TestProactiveNotificationListResponse:
    """Tests for ProactiveNotificationListResponse schema."""

    def test_valid_list_response(self) -> None:
        """Should accept valid list with pagination info."""
        uid = uuid4()
        now = datetime.now(tz=UTC)
        notification = ProactiveNotificationResponse(
            id=uid,
            type=ProactiveNotificationType.task_complete,
            priority=NotificationPriority.normal,
            title="Task done",
            body="Completed",
            source="system",
            is_read=False,
            created_at=now,
        )
        resp = ProactiveNotificationListResponse(
            notifications=[notification],
            total=1,
            page=1,
            page_size=20,
        )
        assert len(resp.notifications) == 1
        assert resp.total == 1
        assert resp.page == 1
        assert resp.page_size == 20

    def test_empty_list_response(self) -> None:
        """Should accept empty list."""
        resp = ProactiveNotificationListResponse(
            notifications=[],
            total=0,
            page=1,
            page_size=20,
        )
        assert len(resp.notifications) == 0
        assert resp.total == 0


class TestUnreadCountResponse:
    """Tests for UnreadCountResponse schema."""

    def test_valid_count(self) -> None:
        """Should store count value."""
        resp = UnreadCountResponse(count=5)
        assert resp.count == 5

    def test_zero_count(self) -> None:
        """Should accept zero count."""
        resp = UnreadCountResponse(count=0)
        assert resp.count == 0


class TestMarkAllReadResponse:
    """Tests for MarkAllReadResponse schema."""

    def test_valid_marked_count(self) -> None:
        """Should store marked_count."""
        resp = MarkAllReadResponse(marked_count=3)
        assert resp.marked_count == 3


class TestCreateProactiveNotification:
    """Tests for CreateProactiveNotification internal schema."""

    def test_valid_create_payload(self) -> None:
        """Should accept valid creation payload."""
        uid = uuid4()
        payload = CreateProactiveNotification(
            user_id=uid,
            type=ProactiveNotificationType.pr_merged,
            title="PR merged",
            body="Feature merged",
            source="github",
        )
        assert payload.user_id == uid
        assert payload.priority == NotificationPriority.normal
        assert payload.source_event is None
        assert payload.metadata == {}

    def test_create_with_all_fields(self) -> None:
        """Should accept all optional fields."""
        uid = uuid4()
        payload = CreateProactiveNotification(
            user_id=uid,
            type=ProactiveNotificationType.ci_failure,
            priority=NotificationPriority.urgent,
            title="CI Failed",
            body="Pipeline broken",
            source="github",
            source_event="github:workflow:123",
            deep_link="https://example.com",
            metadata={"repo": "test"},
        )
        assert payload.priority == NotificationPriority.urgent
        assert payload.source_event == "github:workflow:123"
        assert payload.deep_link == "https://example.com"

    def test_create_missing_required_fields(self) -> None:
        """Should reject missing required fields."""
        with pytest.raises(ValidationError):
            CreateProactiveNotification(
                type=ProactiveNotificationType.suggestion,
                title="Test",
                body="Test",
                source="test",
            )  # type: ignore[call-arg]
