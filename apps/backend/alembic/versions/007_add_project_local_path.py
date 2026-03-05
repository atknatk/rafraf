"""Add local_path column to projects table.

Revision ID: 007_add_project_local_path
Revises: 006_add_user_display_name
Create Date: 2026-03-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "007_add_project_local_path"
down_revision: str | None = "006_add_user_display_name"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add local_path column to projects."""
    op.add_column("projects", sa.Column("local_path", sa.String(1024), nullable=True))


def downgrade() -> None:
    """Remove local_path column from projects."""
    op.drop_column("projects", "local_path")
