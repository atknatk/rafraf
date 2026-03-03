"""Device token SQLAlchemy model for push notifications."""

import uuid

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class DeviceToken(Base, UUIDMixin, TimestampMixin):
    """Stores APNs device tokens for push notification delivery."""

    __tablename__ = "device_tokens"
    __table_args__ = (
        UniqueConstraint("user_id", "token", name="uq_device_tokens_user_token"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    platform: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="ios",
    )
    app_version: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )


class NotificationSettings(Base, UUIDMixin, TimestampMixin):
    """Per-user notification category preferences."""

    __tablename__ = "notification_settings"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    task_complete_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
    approval_needed_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
    error_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
    info_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
