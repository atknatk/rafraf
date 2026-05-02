"""add_tasks_table

Revision ID: 468ccd877a6a
Revises: 011_add_webhook_events
Create Date: 2026-04-01 23:59:23.907856

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '468ccd877a6a'
down_revision: str | None = '011_add_webhook_events'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('tasks',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('project_id', sa.UUID(), nullable=True),
    sa.Column('agent_id', sa.String(length=255), nullable=True),
    sa.Column('title', sa.String(length=500), nullable=False),
    sa.Column('prompt', sa.Text(), nullable=False),
    sa.Column('task_type', sa.String(length=50), nullable=False),
    sa.Column('status', sa.String(length=50), nullable=False),
    sa.Column('current_step', sa.String(length=100), nullable=True),
    sa.Column('total_steps', sa.Integer(), nullable=False),
    sa.Column('completed_steps', sa.Integer(), nullable=False),
    sa.Column('progress_pct', sa.Integer(), nullable=False),
    sa.Column('result_summary', sa.Text(), nullable=True),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('claude_session_id', sa.String(length=255), nullable=True),
    sa.Column('claude_task_id', sa.String(length=255), nullable=True),
    sa.Column('live_activity_push_token', sa.String(length=255), nullable=True),
    sa.Column('started_at', sa.String(length=100), nullable=True),
    sa.Column('completed_at', sa.String(length=100), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_tasks_status'), 'tasks', ['status'], unique=False)
    op.create_index(op.f('ix_tasks_user_id'), 'tasks', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_tasks_user_id'), table_name='tasks')
    op.drop_index(op.f('ix_tasks_status'), table_name='tasks')
    op.drop_table('tasks')
