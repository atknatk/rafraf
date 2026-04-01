"""Task SQLAlchemy model for persistent task lifecycle tracking."""

import enum
import uuid

from sqlalchemy import Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class TaskStatus(str, enum.Enum):
    """Task lifecycle status values."""

    QUEUED = "queued"
    PLANNING = "planning"
    IMPLEMENTING = "implementing"
    TESTING = "testing"
    REVIEWING = "reviewing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# Valid state transitions (from -> set of allowed targets)
VALID_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.QUEUED: {TaskStatus.PLANNING},
    TaskStatus.PLANNING: {TaskStatus.IMPLEMENTING, TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED},
    TaskStatus.IMPLEMENTING: {TaskStatus.TESTING, TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED},
    TaskStatus.TESTING: {TaskStatus.REVIEWING, TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED},
    TaskStatus.REVIEWING: {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED},
    TaskStatus.COMPLETED: set(),
    TaskStatus.FAILED: set(),
    TaskStatus.CANCELLED: set(),
}

# Terminal states (no further transitions allowed)
TERMINAL_STATES: set[TaskStatus] = {
    TaskStatus.COMPLETED,
    TaskStatus.FAILED,
    TaskStatus.CANCELLED,
}


class Task(Base, UUIDMixin, TimestampMixin):
    """Task database model for tracking AI pipeline task lifecycle."""

    __tablename__ = "tasks"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    agent_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    title: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        default="",
    )
    prompt: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    task_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="feature",
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=TaskStatus.QUEUED.value,
        index=True,
    )
    current_step: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    total_steps: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=4,
    )
    completed_steps: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    progress_pct: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    result_summary: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    claude_session_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    claude_task_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    live_activity_push_token: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    started_at: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    completed_at: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
