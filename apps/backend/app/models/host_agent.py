"""HostAgent SQLAlchemy model — host agent registry persistence."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class HostAgent(Base, UUIDMixin, TimestampMixin):
    """Persists registered host agents for restart-resilient state."""

    __tablename__ = "host_agents"

    host_id: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
    )
    hostname: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    os: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )
    os_version: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )
    arch: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )
    capabilities: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        server_default="[]",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="offline",
    )
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_resources: Mapped[dict[str, object] | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    connection_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    agent_version: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    dangerously_skip_permissions: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="false",
    )
