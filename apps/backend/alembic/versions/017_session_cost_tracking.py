"""Add per-session cost tracking columns to ``sessions`` (T2.5).

Revision ID: 017_session_cost_tracking
Revises: 016_add_subagents_table
Create Date: 2026-05-02

Per RafRaf V1 production pivot (docs/10 §8 Faz 2, T2.5 in
docs/12_Action_Plan_Tasks.md §6) the bridge already emits
``event.session.result`` carrying the canonical Anthropic cost projection
(``total_cost_usd`` + per-model ``model_usage`` token breakdown — Doc 10
§6.1.2). T1.1 wires the runner to capture both into ``ClaudeCodeResult``
and T2.2 ships the Prometheus counter ``claude_total_cost_usd_total``.
T2.5 adds **DB persistence** so we can answer "what did this user spend
this month?" without scraping Prometheus history (which only retains the
last 14 days at 15s scrape resolution in the dev manifest).

The existing ``sessions`` table already has ``total_cost_usd
NUMERIC(10, 4) NOT NULL DEFAULT 0`` (added in 005, T0.7 deprecated the
write path). T2.5 widens the precision to ``NUMERIC(10, 6)`` because
single-message claude runs frequently bill at sub-cent ($1e-5) granularity
(Doc 10 §8 quotes "0.000142 USD" as a representative low-watermark) and
the legacy ``(10, 4)`` precision rounds those to zero. The widening is
non-destructive — Postgres preserves existing data when growing the
fractional digits of a NUMERIC column.

Schema additions on ``sessions``
--------------------------------
- ``total_cost_usd NUMERIC(10, 6)`` — widened from ``NUMERIC(10, 4)``;
  cumulative cost across the session's lifetime (``COALESCE`` ADD on each
  ``event.session.result``). Stays NOT NULL with default 0 for back-compat.
- ``total_input_tokens INTEGER NULL`` — sum of per-model ``input_tokens``.
- ``total_output_tokens INTEGER NULL`` — sum of per-model ``output_tokens``.
- ``total_cache_creation_tokens INTEGER NULL`` — Anthropic prompt-caching
  WRITE counter (``cache_creation_input_tokens`` in the SDK), tracked
  separately so cost-of-caching analytics work without recomputing.
- ``total_cache_read_tokens INTEGER NULL`` — Anthropic prompt-caching
  READ counter (``cache_read_input_tokens``); always cheaper than
  ``input_tokens`` so worth its own bucket.
- ``cost_updated_at TIMESTAMPTZ NULL`` — last time the runner persisted a
  cost increment. Doubles as the period filter for monthly aggregation
  (``WHERE cost_updated_at >= period_start``).

Indexes
-------
- ``ix_sessions_cost_updated_at`` — single-column B-tree backing the
  ``GET /sessions/cost-summary`` aggregation (filter by period start).
  No need for a composite (user_id, cost_updated_at) yet because the
  endpoint already restricts on ``user_id`` via the ``ix_sessions_user_id``
  index from migration 001 — Postgres can bitmap-AND the two.

Migration chain note
--------------------
``down_revision`` is **016_add_subagents_table** (T1.10 — most recently
landed). This migration is purely additive (new columns + one index) and
does not touch the legacy ``total_tokens_used`` JSONB column from 005, so
the older code path keeps working until callers migrate to the typed
columns. The widening of ``total_cost_usd`` is implemented via
``ALTER COLUMN ... TYPE`` which is a fast metadata-only change in
Postgres 12+ when the new precision strictly contains the old.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "017_session_cost_tracking"
down_revision: str | None = "016_add_subagents_table"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Widen ``total_cost_usd`` precision and add 5 new cost columns + 1 index."""
    # 1. Widen existing total_cost_usd column from (10, 4) → (10, 6).
    op.alter_column(
        "sessions",
        "total_cost_usd",
        existing_type=sa.Numeric(10, 4),
        type_=sa.Numeric(10, 6),
        existing_nullable=False,
        existing_server_default=sa.text("0"),
    )

    # 2. Add the four token-bucket columns (nullable so back-fill is implicit).
    op.add_column(
        "sessions",
        sa.Column("total_input_tokens", sa.Integer(), nullable=True),
    )
    op.add_column(
        "sessions",
        sa.Column("total_output_tokens", sa.Integer(), nullable=True),
    )
    op.add_column(
        "sessions",
        sa.Column("total_cache_creation_tokens", sa.Integer(), nullable=True),
    )
    op.add_column(
        "sessions",
        sa.Column("total_cache_read_tokens", sa.Integer(), nullable=True),
    )

    # 3. Watermark column — last time the runner recorded a cost increment.
    op.add_column(
        "sessions",
        sa.Column("cost_updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    # 4. Index supports the monthly cost-summary aggregation.
    op.create_index(
        "ix_sessions_cost_updated_at",
        "sessions",
        ["cost_updated_at"],
    )


def downgrade() -> None:
    """Drop new columns + index and shrink ``total_cost_usd`` back to (10, 4).

    Shrinking the precision is **lossy** when any persisted value carries
    more than 4 fractional digits — Postgres rounds half-to-even. The
    downgrade is intended for dev-loop alembic round-trips where the table
    is empty or freshly seeded; production rollbacks should snapshot the
    table first (the standard ``backup-dev-db.sh`` script handles this for
    dev environments).
    """
    op.drop_index("ix_sessions_cost_updated_at", table_name="sessions")
    op.drop_column("sessions", "cost_updated_at")
    op.drop_column("sessions", "total_cache_read_tokens")
    op.drop_column("sessions", "total_cache_creation_tokens")
    op.drop_column("sessions", "total_output_tokens")
    op.drop_column("sessions", "total_input_tokens")
    op.alter_column(
        "sessions",
        "total_cost_usd",
        existing_type=sa.Numeric(10, 6),
        type_=sa.Numeric(10, 4),
        existing_nullable=False,
        existing_server_default=sa.text("0"),
    )
