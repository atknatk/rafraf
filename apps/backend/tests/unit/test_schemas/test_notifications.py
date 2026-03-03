"""Unit tests for notification Pydantic schemas."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.notifications import (
    DeviceTokenDeleteRequest,
    DeviceTokenRegisterRequest,
    DeviceTokenRegisterResponse,
    NotificationPayload,
    NotificationSettingsResponse,
    NotificationSettingsUpdateRequest,
    NotificationType,
)


class TestDeviceTokenRegisterRequest:
    """Tests for DeviceTokenRegisterRequest schema validation."""

    def test_valid_register_request(self) -> None:
        """Should accept valid token string."""
        req = DeviceTokenRegisterRequest(token="abc123token")
        assert req.token == "abc123token"
        assert req.platform == "ios"
        assert req.app_version is None

    def test_register_request_with_all_fields(self) -> None:
        """Should accept all optional fields."""
        req = DeviceTokenRegisterRequest(
            token="abc123token",
            platform="ios",
            app_version="1.2.0",
        )
        assert req.platform == "ios"
        assert req.app_version == "1.2.0"

    def test_register_request_empty_token(self) -> None:
        """Should reject empty token."""
        with pytest.raises(ValidationError):
            DeviceTokenRegisterRequest(token="")

    def test_register_request_missing_token(self) -> None:
        """Should require token field."""
        with pytest.raises(ValidationError):
            DeviceTokenRegisterRequest()  # type: ignore[call-arg]

    def test_register_request_token_max_length(self) -> None:
        """Should reject token longer than 512 characters."""
        with pytest.raises(ValidationError):
            DeviceTokenRegisterRequest(token="x" * 513)


class TestDeviceTokenDeleteRequest:
    """Tests for DeviceTokenDeleteRequest schema validation."""

    def test_valid_delete_request(self) -> None:
        """Should accept valid token string."""
        req = DeviceTokenDeleteRequest(token="abc123token")
        assert req.token == "abc123token"

    def test_delete_request_empty_token(self) -> None:
        """Should reject empty token."""
        with pytest.raises(ValidationError):
            DeviceTokenDeleteRequest(token="")

    def test_delete_request_missing_token(self) -> None:
        """Should require token field."""
        with pytest.raises(ValidationError):
            DeviceTokenDeleteRequest()  # type: ignore[call-arg]


class TestDeviceTokenRegisterResponse:
    """Tests for DeviceTokenRegisterResponse schema."""

    def test_valid_response(self) -> None:
        """Should store id and registered_at."""
        uid = uuid4()
        now = datetime.now(tz=timezone.utc)
        resp = DeviceTokenRegisterResponse(id=uid, registered_at=now)
        assert resp.id == uid
        assert resp.registered_at == now

    def test_response_is_frozen(self) -> None:
        """Should be immutable (frozen)."""
        uid = uuid4()
        now = datetime.now(tz=timezone.utc)
        resp = DeviceTokenRegisterResponse(id=uid, registered_at=now)
        with pytest.raises(ValidationError):
            resp.id = uuid4()  # type: ignore[misc]


class TestNotificationSettingsResponse:
    """Tests for NotificationSettingsResponse schema."""

    def test_valid_settings_response(self) -> None:
        """Should store all boolean fields."""
        resp = NotificationSettingsResponse(
            task_complete_enabled=True,
            approval_needed_enabled=False,
            error_enabled=True,
            info_enabled=False,
        )
        assert resp.task_complete_enabled is True
        assert resp.approval_needed_enabled is False
        assert resp.error_enabled is True
        assert resp.info_enabled is False

    def test_settings_response_is_frozen(self) -> None:
        """Should be immutable (frozen)."""
        resp = NotificationSettingsResponse(
            task_complete_enabled=True,
            approval_needed_enabled=True,
            error_enabled=True,
            info_enabled=True,
        )
        with pytest.raises(ValidationError):
            resp.task_complete_enabled = False  # type: ignore[misc]


class TestNotificationSettingsUpdateRequest:
    """Tests for NotificationSettingsUpdateRequest schema."""

    def test_partial_update(self) -> None:
        """Should allow partial updates (all fields optional)."""
        req = NotificationSettingsUpdateRequest(task_complete_enabled=False)
        assert req.task_complete_enabled is False
        assert req.approval_needed_enabled is None
        assert req.error_enabled is None
        assert req.info_enabled is None

    def test_empty_update(self) -> None:
        """Should allow empty update (no changes)."""
        req = NotificationSettingsUpdateRequest()
        assert req.task_complete_enabled is None

    def test_full_update(self) -> None:
        """Should accept all fields."""
        req = NotificationSettingsUpdateRequest(
            task_complete_enabled=True,
            approval_needed_enabled=False,
            error_enabled=True,
            info_enabled=False,
        )
        assert req.task_complete_enabled is True
        assert req.approval_needed_enabled is False


class TestNotificationType:
    """Tests for NotificationType enum."""

    def test_all_types_exist(self) -> None:
        """Should have exactly 4 notification types."""
        assert len(NotificationType) == 4
        assert NotificationType.task_complete.value == "task_complete"
        assert NotificationType.approval_needed.value == "approval_needed"
        assert NotificationType.error.value == "error"
        assert NotificationType.info.value == "info"


class TestNotificationPayload:
    """Tests for NotificationPayload schema."""

    def test_valid_payload(self) -> None:
        """Should accept valid payload."""
        uid = uuid4()
        payload = NotificationPayload(
            notification_id=uid,
            type=NotificationType.task_complete,
            title="Task Done",
            body="Your task was completed.",
        )
        assert payload.notification_id == uid
        assert payload.type == NotificationType.task_complete
        assert payload.deep_link is None
        assert payload.badge_count == 0
        assert payload.metadata == {}

    def test_payload_with_optional_fields(self) -> None:
        """Should accept optional deep_link and metadata."""
        uid = uuid4()
        payload = NotificationPayload(
            notification_id=uid,
            type=NotificationType.approval_needed,
            title="Approval",
            body="Needs your approval.",
            deep_link="rafraf://approval/123",
            badge_count=5,
            metadata={"project_id": "proj-x"},
        )
        assert payload.deep_link == "rafraf://approval/123"
        assert payload.badge_count == 5
        assert payload.metadata == {"project_id": "proj-x"}

    def test_payload_is_frozen(self) -> None:
        """Should be immutable (frozen)."""
        uid = uuid4()
        payload = NotificationPayload(
            notification_id=uid,
            type=NotificationType.info,
            title="Info",
            body="Just info.",
        )
        with pytest.raises(ValidationError):
            payload.title = "Changed"  # type: ignore[misc]
