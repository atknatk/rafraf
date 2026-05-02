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
    # V1.4 — bridge ``permission_request`` correlation. NULL for the
    # legacy orchestrator-mediated path (in-app approvals); populated
    # when the row originates from a bridge envelope so the
    # ``_await_and_dispatch_decision`` helper can route the reply
    # ``command.claude.permission.{allow,deny}`` envelope back.
    request_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )
    bridge_host_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    rpc_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )
    # Bridge-suggested deadline, distinct from ``timeout_seconds`` (which
    # is the per-category default ApprovalService applies); persisted so
    # operators can correlate per-request UX latency with policy.
    bridge_timeout_seconds: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
