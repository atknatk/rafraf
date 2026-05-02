"""Add projects table.

Revision ID: 003_add_projects
Revises: 002_add_cost_logs
Create Date: 2026-03-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, UUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003_add_projects"
down_revision: str | None = "002_add_cost_logs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create projects table."""
    op.create_table(
        "projects",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="active"),
        sa.Column("repository_url", sa.String(512), nullable=True),
        sa.Column("tech_stack", ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("source", sa.String(50), nullable=False, server_default="manual"),
        sa.Column("last_activity_at", sa.String(50), nullable=True),
        sa.Column("last_activity_summary", sa.Text(), nullable=True),
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
    op.create_index("ix_projects_status", "projects", ["status"])
    op.create_index("ix_projects_name", "projects", ["name"])
    op.create_index(
        "ix_projects_repository_url",
        "projects",
        ["repository_url"],
        unique=True,
        postgresql_where=sa.text("repository_url IS NOT NULL"),
    )


def downgrade() -> None:
    """Drop projects table."""
    op.drop_index("ix_projects_repository_url", table_name="projects")
    op.drop_index("ix_projects_name", table_name="projects")
    op.drop_index("ix_projects_status", table_name="projects")
    op.drop_table("projects")
