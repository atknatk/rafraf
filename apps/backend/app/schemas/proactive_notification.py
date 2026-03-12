"""Pydantic schemas for proactive notification endpoints."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ProactiveNotificationType(StrEnum):
    """Proactive notification type categories."""

    task_complete = "task_complete"
    issue_detected = "issue_detected"
    suggestion = "suggestion"
    reminder = "reminder"
    ci_failure = "ci_failure"
    pr_merged = "pr_merged"
    security_alert = "security_alert"


class NotificationPriority(StrEnum):
    """Notification priority levels."""

    urgent = "urgent"
    normal = "normal"
    low = "low"


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class ProactiveNotificationResponse(BaseModel):
    """Single proactive notification response."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    type: ProactiveNotificationType
    priority: NotificationPriority
    title: str
    body: str
    source: str
    source_event: str | None = None
    deep_link: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)
    is_read: bool
    read_at: datetime | None = None
    created_at: datetime


class ProactiveNotificationListResponse(BaseModel):
    """Paginated list of proactive notifications."""

    model_config = ConfigDict(frozen=True)

    notifications: list[ProactiveNotificationResponse]
    total: int
    page: int
    page_size: int


class UnreadCountResponse(BaseModel):
    """Unread notification count response."""

    model_config = ConfigDict(frozen=True)

    count: int


class MarkAllReadResponse(BaseModel):
    """Response after marking all notifications as read."""

    model_config = ConfigDict(frozen=True)

    marked_count: int


# ---------------------------------------------------------------------------
# Internal models (for service layer)
# ---------------------------------------------------------------------------


class CreateProactiveNotification(BaseModel):
    """Internal schema for creating a proactive notification."""

    user_id: UUID
    type: ProactiveNotificationType
    priority: NotificationPriority = NotificationPriority.normal
    title: str
    body: str
    source: str
    source_event: str | None = None
    deep_link: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)
