"""Add pulse_reports table.

Revision ID: 008_add_pulse_reports_table
Revises: 007_add_project_local_path
Create Date: 2026-03-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON, UUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "008_add_pulse_reports_table"
down_revision: str | None = "007_add_project_local_path"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create pulse_reports table."""
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


def downgrade() -> None:
    """Drop pulse_reports table."""
    op.drop_index("ix_pulse_reports_report_date", table_name="pulse_reports")
    op.drop_index("ix_pulse_reports_user_id", table_name="pulse_reports")
    op.drop_index("ix_pulse_reports_project_id", table_name="pulse_reports")
    op.drop_table("pulse_reports")
