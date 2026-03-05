"""AgentProject SQLAlchemy model — agent-proje iliskisi."""

import uuid

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class AgentProject(Base, UUIDMixin, TimestampMixin):
    """Agent ile proje arasindaki M:N iliskiyi temsil eder.

    Ayni proje birden fazla agent'ta olabilir.
    Her kayit, bir agent'in belirli bir projeye erisimini ve aktifligini tutar.
    """

    __tablename__ = "agent_projects"
    __table_args__ = (
        UniqueConstraint("agent_id", "project_id", name="uq_agent_project"),
    )

    agent_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
