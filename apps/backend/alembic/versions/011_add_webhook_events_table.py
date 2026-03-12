"""Add webhook_events table for GitHub webhook persistence and idempotency.

Revision ID: 011_add_webhook_events
Revises: 010_agent_skip_perms
Create Date: 2026-03-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "011_add_webhook_events"
down_revision: str | None = "010_agent_skip_perms"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create webhook_events table."""
    op.create_table(
        "webhook_events",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("delivery_id", sa.String(255), nullable=False, unique=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("action", sa.String(100), nullable=False, server_default=""),
        sa.Column("repo", sa.String(255), nullable=False, server_default=""),
        sa.Column("sender", sa.String(255), nullable=False, server_default=""),
        sa.Column("summary", JSONB, nullable=False, server_default="{}"),
        sa.Column("processed", sa.Boolean(), nullable=False, server_default="false"),
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
    op.create_index("ix_webhook_events_delivery_id", "webhook_events", ["delivery_id"])
    op.create_index("ix_webhook_events_event_type", "webhook_events", ["event_type"])
    op.create_index(
        "ix_webhook_events_created_at",
        "webhook_events",
        [sa.text("created_at DESC")],
    )


def downgrade() -> None:
    """Drop webhook_events table."""
    op.drop_index("ix_webhook_events_created_at", table_name="webhook_events")
    op.drop_index("ix_webhook_events_event_type", table_name="webhook_events")
    op.drop_index("ix_webhook_events_delivery_id", table_name="webhook_events")
    op.drop_table("webhook_events")
