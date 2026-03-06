"""ApprovalRequest SQLAlchemy model — persistent approval requests."""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDMixin


class ApprovalRequest(Base, UUIDMixin):
    """Persists approval requests so they survive process restarts."""

    __tablename__ = "approval_requests"

    session_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    connection_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    tool_name: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    action: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    params: Mapped[dict[str, object] | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    category: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
    )
    timeout_seconds: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=300,
    )
    timeout_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    responded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
