"""Add dangerously_skip_permissions to host_agents table.

Revision ID: 010_add_agent_dangerously_skip_permissions
Revises: 009_add_message_ratings
Create Date: 2026-03-06
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "010_agent_skip_perms"
down_revision: str | None = "009_add_message_ratings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add dangerously_skip_permissions column to host_agents."""
    op.add_column(
        "host_agents",
        sa.Column(
            "dangerously_skip_permissions",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )


def downgrade() -> None:
    """Remove dangerously_skip_permissions column from host_agents."""
    op.drop_column("host_agents", "dangerously_skip_permissions")
