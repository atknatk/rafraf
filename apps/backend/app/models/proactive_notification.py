"""Proactive notification SQLAlchemy model."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class ProactiveNotification(Base, UUIDMixin, TimestampMixin):
    """Stores proactive notifications triggered by AI, GitHub events, etc."""

    __tablename__ = "proactive_notifications"
    __table_args__ = (
        Index(
            "idx_proactive_notifications_user_unread",
            "user_id",
            "is_read",
            postgresql_where=text("is_read = FALSE"),
        ),
        Index(
            "idx_proactive_notifications_created_at",
            "created_at",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    priority: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="normal",
    )
    title: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )
    body: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    source: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    source_event: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )
    deep_link: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
    )
    metadata_json: Mapped[dict[str, str]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
    )
    is_read: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
