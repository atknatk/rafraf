"""Add cost_logs table.

Revision ID: 002_add_cost_logs
Revises: 001_add_users
Create Date: 2026-03-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "002_add_cost_logs"
down_revision: str | None = "001_add_users"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create cost_logs table."""
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


def downgrade() -> None:
    """Drop cost_logs table."""
    op.drop_index("ix_cost_logs_called_at", table_name="cost_logs")
    op.drop_index("ix_cost_logs_model", table_name="cost_logs")
    op.drop_index("ix_cost_logs_user_id", table_name="cost_logs")
    op.drop_table("cost_logs")
