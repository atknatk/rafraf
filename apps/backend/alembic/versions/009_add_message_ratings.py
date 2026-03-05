"""Add rating fields to messages table.

Revision ID: 009_add_message_ratings
Revises: 008_add_pulse_reports_table
Create Date: 2026-03-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op  # noqa: E402

# revision identifiers, used by Alembic.
revision: str = "009_add_message_ratings"
down_revision: str | None = "008_add_pulse_reports_table"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add rating, rating_note, rated_at columns to messages table."""
    op.add_column("messages", sa.Column("rating", sa.String(10), nullable=True))
    op.add_column("messages", sa.Column("rating_note", sa.String(500), nullable=True))
    op.add_column(
        "messages",
        sa.Column("rated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_messages_rating", "messages", ["rating"])


def downgrade() -> None:
    """Remove rating columns from messages table."""
    op.drop_index("ix_messages_rating", table_name="messages")
    op.drop_column("messages", "rated_at")
    op.drop_column("messages", "rating_note")
    op.drop_column("messages", "rating")
