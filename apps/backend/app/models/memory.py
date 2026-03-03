"""ProjectMemory SQLAlchemy model for structured project-level memory."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class ProjectMemory(Base, UUIDMixin, TimestampMixin):
    """Stores structured project-level memories (tech_stack, known_issues, etc.).

    Each record represents a single fact about a project, identified by
    (project_id, category, key) unique constraint. Supports UPSERT semantics.
    """

    __tablename__ = "project_memory"
    __table_args__ = (
        UniqueConstraint("project_id", "category", "key", name="uq_project_memory_pckey"),
        Index("idx_project_memory_project_id", "project_id"),
        Index("idx_project_memory_category", "project_id", "category"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    category: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    key: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    value: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
    )
    confidence: Mapped[float] = mapped_column(
        Float,
        default=1.0,
        nullable=False,
    )
    source: Mapped[str] = mapped_column(
        String(50),
        default="ai_inferred",
        nullable=False,
    )
    last_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )
