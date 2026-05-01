"""Subagent SQLAlchemy model — Agent Teams subagent state DB projection.

Persists the per-subagent metadata that the Go bridge captures in-memory in
``apps/rafraf-bridge/internal/claude/state.go`` (``SubagentState``). T1.1
will wire the bridge's ``session.subagent_*`` events into
``SubagentRepository.upsert_subagent`` so the table stays in sync with the
parser's view of the world.

Per docs/10 §6.1.1 + §6.1.2 (Production Pivot Spec) and docs/11 §6 (Bridge
Spec). Created by alembic 016.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.bridge import Bridge


class Subagent(Base):
    """One row per subagent task spawned by ``claude -p`` Agent Teams.

    Lifecycle: INSERT on ``system/task_started`` (bridge → backend), UPDATE
    on ``system/task_progress`` (rare; CLI seldom emits this), UPDATE on
    ``system/task_notification`` to record terminal status + usage.

    Persistence is "best effort" — a bridge crash mid-stream may leave a
    subagent stuck in ``status='spawned'``. Reconciliation is a future-V2
    concern.
    """

    __tablename__ = "subagents"
    __table_args__ = (
        UniqueConstraint("session_id", "task_id", name="subagents_task_session_uniq"),
    )

    # ── identity ──
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # ── ownership ──
    bridge_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bridges.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    session_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    task_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    parent_session_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    # ── descriptive metadata (from system/task_started) ──
    name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    prompt_preview: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    subagent_type: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    isolation: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )

    # ── lifecycle status ──
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="spawned",
        server_default="spawned",
        index=True,
    )

    # ── terminal payload (from system/task_notification) ──
    summary: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    total_tokens: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    tool_uses: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    duration_ms: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    # ── timestamps ──
    spawned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # ── ORM relationships ──
    bridge: Mapped[Bridge] = relationship(
        "Bridge",
        back_populates="subagents",
    )
