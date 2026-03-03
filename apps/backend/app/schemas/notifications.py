"""Pydantic schemas for push notification endpoints."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class NotificationType(StrEnum):
    """Push notification category types."""

    task_complete = "task_complete"
    approval_needed = "approval_needed"
    error = "error"
    info = "info"


# ---------------------------------------------------------------------------
# Device token
# ---------------------------------------------------------------------------


class DeviceTokenRegisterRequest(BaseModel):
    """Request to register an APNs device token."""

    token: str = Field(
        ...,
        min_length=1,
        max_length=512,
        description="APNs device token",
    )
    platform: str = Field(
        default="ios",
        description="Platform (ios)",
    )
    app_version: str | None = Field(
        default=None,
        description="Application version string",
    )


class DeviceTokenRegisterResponse(BaseModel):
    """Response after successful device token registration."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    registered_at: datetime


class DeviceTokenDeleteRequest(BaseModel):
    """Request to deactivate an APNs device token (e.g. on logout)."""

    token: str = Field(
        ...,
        min_length=1,
        max_length=512,
        description="APNs device token to deactivate",
    )


# ---------------------------------------------------------------------------
# Notification settings
# ---------------------------------------------------------------------------


class NotificationSettingsResponse(BaseModel):
    """Current notification preferences for the user."""

    model_config = ConfigDict(frozen=True)

    task_complete_enabled: bool
    approval_needed_enabled: bool
    error_enabled: bool
    info_enabled: bool


class NotificationSettingsUpdateRequest(BaseModel):
    """Partial update of notification preferences."""

    task_complete_enabled: bool | None = None
    approval_needed_enabled: bool | None = None
    error_enabled: bool | None = None
    info_enabled: bool | None = None


# ---------------------------------------------------------------------------
# Notification payload (sent over WS or APNs)
# ---------------------------------------------------------------------------


class NotificationPayload(BaseModel):
    """Payload pushed to the client (WS in-app or APNs remote)."""

    model_config = ConfigDict(frozen=True)

    notification_id: UUID
    type: NotificationType
    title: str
    body: str
    deep_link: str | None = None
    badge_count: int = 0
    metadata: dict[str, str] = Field(default_factory=dict)
