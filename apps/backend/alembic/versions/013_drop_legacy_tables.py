"""Drop legacy tables: cost_logs, pulse_reports, project_memory.

Revision ID: 013_drop_legacy_tables
Revises: 468ccd877a6a
Create Date: 2026-05-01

Per RafRaf v0.1 production pivot (docs/10 §5.7 + ADR-0004), these tables back
features that have been deferred to V2:

- ``cost_logs`` — backed cost service (deleted in T0.7+T0.8). Cost tracking is
  V2 scope.
- ``pulse_reports`` — backed pulse feature (deleted in T0.4+T0.8). Daily
  digest reports are V2 scope.
- ``project_memory`` — only mem0-related table actually present in the schema
  (introduced in 004 alongside the now-deferred mem0 services). mem0 is V2
  scope per ADR-0004.

The downgrade path re-creates each table with the column definitions from
their original CREATE migrations (002, 008, 004 respectively) so the migration
is reversible for local development. For a production-grade restore, prefer
the database dump captured in T0.1 (``~/Code/rafraf-backups/``) since data
inside the dropped tables is **not** preserved by ``alembic downgrade``.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSON, JSONB, UUID

# revision identifiers, used by Alembic.
revision: str = "013_drop_legacy_tables"
down_revision: str | None = "468ccd877a6a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop cost_logs, pulse_reports, and project_memory tables."""
    # ── project_memory (from 004_add_remaining_tables) ──
    op.drop_index("idx_project_memory_category", table_name="project_memory")
    op.drop_index("idx_project_memory_project_id", table_name="project_memory")
    op.drop_table("project_memory")

    # ── pulse_reports (from 008_add_pulse_reports_table) ──
    op.drop_index("ix_pulse_reports_report_date", table_name="pulse_reports")
    op.drop_index("ix_pulse_reports_user_id", table_name="pulse_reports")
    op.drop_index("ix_pulse_reports_project_id", table_name="pulse_reports")
    op.drop_table("pulse_reports")

    # ── cost_logs (from 002_add_cost_logs_table) ──
    op.drop_index("ix_cost_logs_called_at", table_name="cost_logs")
    op.drop_index("ix_cost_logs_model", table_name="cost_logs")
    op.drop_index("ix_cost_logs_user_id", table_name="cost_logs")
    op.drop_table("cost_logs")


def downgrade() -> None:
    """Re-create dropped tables (schema only — data is not restored)."""
    # ── cost_logs ──
    op.create_table(
        "cost_logs",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Float(), nullable=False),
        sa.Column("session_id", sa.String(255), nullable=True),
        sa.Column("tool_name", sa.String(100), nullable=True),
        sa.Column(
            "called_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_cost_logs_user_id", "cost_logs", ["user_id"])
    op.create_index("ix_cost_logs_model", "cost_logs", ["model"])
    op.create_index("ix_cost_logs_called_at", "cost_logs", ["called_at"])

    # ── pulse_reports ──
    op.create_table(
        "pulse_reports",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("project_id", UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("report_date", sa.Date(), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total_messages", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("user_messages", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("assistant_messages", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("total_cost_usd", sa.Float(), nullable=True),
        sa.Column("models_used", JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("summary_text", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("completed_items", JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("in_progress_items", JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("risks", JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("suggestions", JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("raw_stats", JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_pulse_reports_project_id", "pulse_reports", ["project_id"])
    op.create_index("ix_pulse_reports_user_id", "pulse_reports", ["user_id"])
    op.create_index("ix_pulse_reports_report_date", "pulse_reports", ["report_date"])

    # ── project_memory ──
    op.create_table(
        "project_memory",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("project_id", UUID(as_uuid=True), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("value", JSONB(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default=sa.text("1.0")),
        sa.Column("source", sa.String(50), nullable=False, server_default=sa.text("'ai_inferred'")),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("project_id", "category", "key", name="uq_project_memory_pckey"),
    )
    op.create_index("idx_project_memory_project_id", "project_memory", ["project_id"])
    op.create_index("idx_project_memory_category", "project_memory", ["project_id", "category"])
