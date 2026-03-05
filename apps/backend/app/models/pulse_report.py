"""Pulse Report SQLAlchemy modeli — günlük AI proje özeti."""

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, Integer, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class PulseReport(Base, UUIDMixin, TimestampMixin):
    """Günlük AI proje özeti kayıt modeli.

    Her proje için periyodik olarak AI tarafından oluşturulan
    yapılandırılmış proje durum raporu.
    """

    __tablename__ = "pulse_reports"

    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    report_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )
    period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    period_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    total_messages: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    user_messages: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    assistant_messages: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    total_cost_usd: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )
    models_used: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    summary_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )
    completed_items: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    in_progress_items: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    risks: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    suggestions: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    raw_stats: Mapped[dict[str, object] | None] = mapped_column(
        JSON,
        nullable=True,
    )
