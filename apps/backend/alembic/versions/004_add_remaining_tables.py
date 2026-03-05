"""Add remaining tables: messages, agent_projects, device_tokens, notification_settings, project_memory.

Revision ID: 004_add_remaining_tables
Revises: 003_add_projects
Create Date: 2026-03-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision: str = "004_add_remaining_tables"
down_revision: str | None = "003_add_projects"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create messages, agent_projects, device_tokens, notification_settings, project_memory tables."""
    # ── messages ──
    op.create_table(
        "messages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", sa.String(255), nullable=False),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True),
        sa.Column("agent_id", sa.String(255), nullable=True),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("model_used", sa.String(100), nullable=True),
        sa.Column("tokens_used", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_messages_session_id", "messages", ["session_id"])
    op.create_index("ix_messages_user_id", "messages", ["user_id"])
    op.create_index("ix_messages_project_id", "messages", ["project_id"])

    # ── agent_projects ──
    op.create_table(
        "agent_projects",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("agent_id", sa.String(255), nullable=False),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("agent_id", "project_id", name="uq_agent_project"),
    )
    op.create_index("ix_agent_projects_agent_id", "agent_projects", ["agent_id"])
    op.create_index("ix_agent_projects_project_id", "agent_projects", ["project_id"])

    # ── device_tokens ──
    op.create_table(
        "device_tokens",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token", sa.Text(), nullable=False),
        sa.Column("platform", sa.String(16), nullable=False, server_default=sa.text("'ios'")),
        sa.Column("app_version", sa.String(32), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "token", name="uq_device_tokens_user_token"),
    )
    op.create_index("ix_device_tokens_user_id", "device_tokens", ["user_id"])

    # ── notification_settings ──
    op.create_table(
        "notification_settings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("task_complete_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("approval_needed_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("error_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("info_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_notification_settings_user_id", "notification_settings", ["user_id"])

    # ── project_memory ──
    op.create_table(
        "project_memory",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", UUID(as_uuid=True), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("value", JSONB(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default=sa.text("1.0")),
        sa.Column("source", sa.String(50), nullable=False, server_default=sa.text("'ai_inferred'")),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("project_id", "category", "key", name="uq_project_memory_pckey"),
    )
    op.create_index("idx_project_memory_project_id", "project_memory", ["project_id"])
    op.create_index("idx_project_memory_category", "project_memory", ["project_id", "category"])


def downgrade() -> None:
    """Drop all five tables."""
    op.drop_index("idx_project_memory_category", table_name="project_memory")
    op.drop_index("idx_project_memory_project_id", table_name="project_memory")
    op.drop_table("project_memory")

    op.drop_index("ix_notification_settings_user_id", table_name="notification_settings")
    op.drop_table("notification_settings")

    op.drop_index("ix_device_tokens_user_id", table_name="device_tokens")
    op.drop_table("device_tokens")

    op.drop_index("ix_agent_projects_project_id", table_name="agent_projects")
    op.drop_index("ix_agent_projects_agent_id", table_name="agent_projects")
    op.drop_table("agent_projects")

    op.drop_index("ix_messages_project_id", table_name="messages")
    op.drop_index("ix_messages_user_id", table_name="messages")
    op.drop_index("ix_messages_session_id", table_name="messages")
    op.drop_table("messages")
