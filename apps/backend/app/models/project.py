"""Project SQLAlchemy model."""

from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class Project(Base, UUIDMixin, TimestampMixin):
    """Project database model for tracking managed projects."""

    __tablename__ = "projects"

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="active",
        index=True,
    )
    repository_url: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
    )
    local_path: Mapped[str | None] = mapped_column(
        String(1024),
        nullable=True,
    )
    tech_stack: Mapped[list[str]] = mapped_column(
        ARRAY(String),
        nullable=False,
        default=list,
    )
    source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="manual",
    )
    last_activity_at: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    last_activity_summary: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
