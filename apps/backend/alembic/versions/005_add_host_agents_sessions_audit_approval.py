"""Add host_agents, sessions, audit_log, approval_requests tables.

Revision ID: 005_add_core_tables
Revises: 004_add_remaining_tables
Create Date: 2026-03-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision: str = "005_add_core_tables"
down_revision: str | None = "004_add_remaining_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create host_agents, sessions, audit_log, approval_requests tables."""
    # ── host_agents ──
    op.create_table(
        "host_agents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("host_id", sa.String(50), nullable=False, unique=True),
        sa.Column("hostname", sa.String(100), nullable=True),
        sa.Column("os", sa.String(20), nullable=True),
        sa.Column("os_version", sa.String(20), nullable=True),
        sa.Column("arch", sa.String(20), nullable=True),
        sa.Column("capabilities", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'offline'")),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_resources", JSONB(), nullable=True),
        sa.Column("connection_id", sa.String(255), nullable=True),
        sa.Column("agent_version", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # ── sessions ──
    op.create_table(
        "sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("message_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("total_tokens_used", JSONB(), nullable=False, server_default=sa.text("'{\"input\": 0, \"output\": 0}'::jsonb")),
        sa.Column("total_cost_usd", sa.Numeric(10, 4), nullable=False, server_default=sa.text("0")),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])

    # ── audit_log ──
    op.create_table(
        "audit_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", sa.String(255), nullable=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("tool_name", sa.String(50), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True),
        sa.Column("host_id", sa.String(50), nullable=True),
        sa.Column("input_params", JSONB(), nullable=True),
        sa.Column("output_result", JSONB(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("approval_required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("model_used", sa.String(50), nullable=True),
        sa.Column("tokens_used", JSONB(), nullable=True),
        sa.Column("cost_usd", sa.Numeric(10, 6), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_audit_log_session_id", "audit_log", ["session_id"])
    op.create_index("ix_audit_log_user_id", "audit_log", ["user_id"])
    op.create_index("ix_audit_log_tool_name", "audit_log", ["tool_name"])

    # ── approval_requests ──
    op.create_table(
        "approval_requests",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", sa.String(255), nullable=False),
        sa.Column("connection_id", sa.String(255), nullable=True),
        sa.Column("tool_name", sa.String(50), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("params", JSONB(), nullable=True),
        sa.Column("category", sa.String(30), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default=sa.text("300")),
        sa.Column("timeout_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_approval_requests_session_id", "approval_requests", ["session_id"])


def downgrade() -> None:
    """Drop all four tables."""
    op.drop_index("ix_approval_requests_session_id", table_name="approval_requests")
    op.drop_table("approval_requests")

    op.drop_index("ix_audit_log_tool_name", table_name="audit_log")
    op.drop_index("ix_audit_log_user_id", table_name="audit_log")
    op.drop_index("ix_audit_log_session_id", table_name="audit_log")
    op.drop_table("audit_log")

    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.drop_table("sessions")

    op.drop_table("host_agents")
