"""Session SQLAlchemy model — user session persistence."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class Session(Base, UUIDMixin, TimestampMixin):
    """Persists WebSocket session lifecycle for audit and analytics.

    Cost columns (``total_cost_usd`` + token buckets + ``cost_updated_at``)
    are populated by ``ClaudeCodeRunner._dispatch_event`` when an
    ``event.session.result`` envelope arrives (Doc 10 §6.1.2 / T2.5). The
    update is cumulative ADD via ``COALESCE`` so multi-turn sessions
    correctly aggregate across many ``claude -p`` runs.
    """

    __tablename__ = "sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    message_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    total_tokens_used: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        server_default='{"input": 0, "output": 0}',
    )
    # Numeric(10, 6) — widened from (10, 4) in alembic 017 to avoid rounding
    # sub-cent claude runs (Doc 10 §8 quotes 0.000142 USD as a reference
    # low-watermark; legacy precision rounded those to 0).
    total_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 6),
        nullable=False,
        default=Decimal("0"),
    )
    # Per-bucket token counters (T2.5). Nullable because pre-T2.5 rows have
    # no value and we keep the schema additive — readers must coalesce to 0.
    total_input_tokens: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    total_output_tokens: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    total_cache_creation_tokens: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    total_cache_read_tokens: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    cost_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    summary: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
