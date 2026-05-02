"""Add subagents table — Agent Teams subagent state DB projection.

Revision ID: 016_add_subagents_table
Revises: 014_rename_host_agents_bridges
Create Date: 2026-05-02

Per RafRaf V1 production pivot (docs/10 §6.1.1 + §6.1.2, T1.10) the bridge
already keeps an in-memory map of subagents spawned by ``claude -p`` under
``CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`` (see
``apps/rafraf-bridge/internal/claude/state.go``). T1.10 adds **persistence**
of that state via this ``subagents`` table so the backend can answer
restart-resilient queries like "which subagents ran in this session?" and
"what was the terminal status / token usage?".

Schema
------
- ``id UUID PRIMARY KEY`` — generated server-side via Postgres 13+ built-in
  ``gen_random_uuid()`` (UUIDv4). UUIDv7 is preferable for time-ordered
  inserts but is not natively available on PG16 without a custom extension
  (uuid_v7 / pg_uuidv7). TODO(V2): swap to UUIDv7 once we standardise on the
  extension across all envs.
- ``bridge_id UUID NOT NULL REFERENCES bridges(id) ON DELETE CASCADE`` — the
  bridge that emitted the subagent_spawned event. Deleting a bridge cascades
  to its historical subagents (matches the bridge unregister semantics in
  T1.3 scope).
- ``session_id VARCHAR(64) NOT NULL`` — claude session UUID; links to the
  ``sessions`` table (no FK declared because sessions is owned by T1.1+T1.2
  and the chat → claude session mapping crosses service boundaries).
- ``task_id VARCHAR(64) NOT NULL`` — claude's per-subagent task_id from
  ``system/task_started``. Unique per session.
- ``parent_session_id VARCHAR(64) NULL`` — populated when the bridge knows
  the orchestrator session; null otherwise.
- ``name VARCHAR(255) NULL`` — ``description`` field from the spawn event.
- ``description TEXT NULL`` — long-form description if the CLI provides one.
- ``prompt_preview TEXT NULL`` — first 200 chars of the spawn prompt (the
  bridge already truncates to 280; the column accepts up to whatever
  TEXT supports, so the bridge's truncation is the governing limit).
- ``subagent_type VARCHAR(64) NULL`` — e.g. ``general-purpose``,
  ``Explore``, ``code-reviewer``, plugin-namespaced labels like
  ``dark-factory:holdout-validator``.
- ``isolation VARCHAR(32) NULL`` — ``"worktree"`` if the subagent runs in
  an isolated worktree, otherwise null.
- ``status VARCHAR(32) NOT NULL DEFAULT 'spawned'`` — spawned, in_progress,
  completed, failed (mirrors the bridge ``SubagentState.Status`` field).
- ``summary TEXT NULL`` — terminal summary from ``system/task_notification``.
- ``total_tokens INT NULL`` / ``tool_uses INT NULL`` / ``duration_ms INT NULL``
  — token + tool-use accounting from the completion event.
- ``spawned_at TIMESTAMPTZ NOT NULL`` — when the bridge observed the spawn.
- ``updated_at TIMESTAMPTZ NULL`` — last in-flight progress mutation.
- ``completed_at TIMESTAMPTZ NULL`` — when the bridge observed termination.
- ``created_at TIMESTAMPTZ NOT NULL DEFAULT now()`` — DB row insertion time.

Constraints + indexes
---------------------
- ``UNIQUE (session_id, task_id)`` — claude does not reuse task_ids within a
  session, so the same (session_id, task_id) tuple identifies a subagent
  uniquely. Also acts as the conflict target for upsert.
- ``ix_subagents_bridge_id`` — list "all subagents from this bridge".
- ``ix_subagents_session_id`` — list "all subagents in this session".
- ``ix_subagents_status`` — filter "active subagents" / "failed subagents".

Migration chain note
--------------------
This migration's ``down_revision`` is **014_rename_host_agents_bridges** —
NOT 015. T1.3 (alembic 015 — drop legacy bridge columns) had not landed when
T1.10 was being authored. The orchestrator will fix the chain link to point
at 015 when T1.3 cherry-picks ahead of T1.10. If 015 lands first, the only
edit needed in this file is the ``down_revision`` constant.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "016_add_subagents_table"
# Chained to 015 (T1.3) which lands ahead of T1.10 in the cherry-pick order.
down_revision: str | None = "015_drop_legacy_bridge_columns"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create ``subagents`` table + 3 secondary indexes."""
    op.create_table(
        "subagents",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            # gen_random_uuid() is built into PG13+ (no pgcrypto required).
            # TODO(V2): swap to UUIDv7 once we standardise on uuid_v7 / pg_uuidv7.
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "bridge_id",
            UUID(as_uuid=True),
            sa.ForeignKey("bridges.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("task_id", sa.String(length=64), nullable=False),
        sa.Column("parent_session_id", sa.String(length=64), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("prompt_preview", sa.Text(), nullable=True),
        sa.Column("subagent_type", sa.String(length=64), nullable=True),
        sa.Column("isolation", sa.String(length=32), nullable=True),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'spawned'"),
        ),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("tool_uses", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("spawned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "session_id",
            "task_id",
            name="subagents_task_session_uniq",
        ),
    )
    op.create_index("ix_subagents_bridge_id", "subagents", ["bridge_id"])
    op.create_index("ix_subagents_session_id", "subagents", ["session_id"])
    op.create_index("ix_subagents_status", "subagents", ["status"])


def downgrade() -> None:
    """Drop ``subagents`` table + its indexes."""
    op.drop_index("ix_subagents_status", table_name="subagents")
    op.drop_index("ix_subagents_session_id", table_name="subagents")
    op.drop_index("ix_subagents_bridge_id", table_name="subagents")
    op.drop_table("subagents")
