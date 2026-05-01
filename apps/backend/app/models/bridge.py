"""Bridge SQLAlchemy model — Mac/Linux Go bridge registry persistence.

Replaces the legacy ``HostAgent`` model as part of the V1 production pivot
(docs/10 §6.1.1, T1.4). The Python "host agent" daemon has been archived
(``apps/_archive/agent``) and superseded by the Go bridge in
``apps/rafraf-bridge/``.

The legacy ``HostAgent`` symbol is still exported as an alias from
``app.models`` so that T1.3-scope code (services / routes / repositories that
have not yet been refactored) keeps importing successfully. Remove the alias
once T1.3 lands.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class Bridge(Base, UUIDMixin, TimestampMixin):
    """Persists registered Go bridges for restart-resilient state."""

    __tablename__ = "bridges"

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
    pairing_token: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    bridge_version: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )


# TODO(T1.3): remove this alias after services / repositories / routes stop
# importing ``HostAgent`` and switch to ``Bridge`` directly.
HostAgent = Bridge
