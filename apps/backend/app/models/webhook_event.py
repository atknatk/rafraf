"""WebhookEvent SQLAlchemy model — GitHub webhook event persistence."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDMixin


class WebhookEvent(Base, UUIDMixin):
    """Persisted GitHub webhook event for idempotency and audit trail."""

    __tablename__ = "webhook_events"

    delivery_id: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )
    action: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="",
    )
    repo: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="",
    )
    sender: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="",
    )
    summary: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    processed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
