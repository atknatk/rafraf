"""Add display_name column to users table.

Revision ID: 006_add_user_display_name
Revises: 005_add_core_tables
Create Date: 2026-03-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "006_add_user_display_name"
down_revision: str | None = "005_add_core_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add display_name column to users."""
    op.add_column("users", sa.Column("display_name", sa.String(255), nullable=True))


def downgrade() -> None:
    """Remove display_name column from users."""
    op.drop_column("users", "display_name")
