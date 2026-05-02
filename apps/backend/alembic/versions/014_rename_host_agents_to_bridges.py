"""Rename host_agents to bridges + add pairing_token / bridge_version.

Revision ID: 014_rename_host_agents_bridges
Revises: 013_drop_legacy_tables
Create Date: 2026-05-02

Per RafRaf V1 production pivot (docs/10 §6.1.1, docs/12 Faz 1 / T1.4) the
Python "host agent" concept is being replaced by the Go "bridge"
(``apps/rafraf-bridge/``). This migration is the schema foundation for that
rename — downstream tasks (T1.3 service layer refactor, T1.10 subagent state
projection) build on top of it.

Changes
-------
- ``host_agents`` table is renamed to ``bridges`` (incl. PK + unique
  constraints).
- Two new nullable columns are added:
  * ``pairing_token VARCHAR(64) NULL`` — populated post pairing handshake.
  * ``bridge_version VARCHAR(32) NULL`` — Go bridge release tag (e.g. "0.1.0").

Deviations from the original task brief
---------------------------------------
- ``agent_api_key`` is **not** a column on ``host_agents`` (verified via
  ``\\d host_agents`` on the dev DB and by reading 005 + 010 migrations). It
  only exists as a backend setting (``app.core.config.Settings.agent_api_key``)
  used by ``agent_ws.py`` shared-secret auth. Removing the env var / config
  field is T1.3 scope, not a schema migration concern. No-op here.
- ``dangerously_skip_permissions`` is **kept**. The task brief explicitly says
  "if uncertain, keep it and just rename FK references" and dropping it would
  break ``app.repositories.host_agent_repo.HostAgentRepository.update_settings``
  + the ``PATCH /agents/{host_id}/settings`` route + the ``AgentSettings``
  Pydantic schema, all of which are T1.3 scope. Once T1.3 lands a follow-up
  migration can remove the column cleanly.
- No FK rename is performed because **no other table references**
  ``host_agents`` (verified by inspecting all model files + the live dev DB —
  ``audit_log.host_id`` is a ``VARCHAR(50)`` string, not a FK).
- Only one explicit index exists on the table (``host_agents_host_id_key``,
  the unique constraint backing ``host_id``). It is renamed to
  ``bridges_host_id_key`` via ``op.execute('ALTER INDEX ...')`` because
  ``op.rename_table`` does not rename auto-generated constraint indexes on
  Postgres. Renaming the index also renames the matching constraint
  automatically (Postgres keeps index name = constraint name for PK / UNIQUE
  constraints), so no separate ``RENAME CONSTRAINT`` is required.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "014_rename_host_agents_bridges"
down_revision: str | None = "013_drop_legacy_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Rename host_agents → bridges and add bridge-specific columns."""
    # ── rename table ──
    op.rename_table("host_agents", "bridges")

    # ── rename auto-named PK + unique constraint indexes ──
    # rename_table does not touch index/constraint names on Postgres. Renaming
    # the backing index also renames the matching PK/UNIQUE constraint
    # (Postgres keeps the two names in sync), so no separate
    # ``RENAME CONSTRAINT`` is needed.
    op.execute("ALTER INDEX host_agents_pkey RENAME TO bridges_pkey")
    op.execute("ALTER INDEX host_agents_host_id_key RENAME TO bridges_host_id_key")

    # ── add bridge-specific columns ──
    op.add_column(
        "bridges",
        sa.Column("pairing_token", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "bridges",
        sa.Column("bridge_version", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    """Reverse the rename + drop the bridge-specific columns."""
    # ── drop added columns ──
    op.drop_column("bridges", "bridge_version")
    op.drop_column("bridges", "pairing_token")

    # ── rename indexes back (renaming the index also renames the matching
    # PK/UNIQUE constraint on Postgres) ──
    op.execute("ALTER INDEX bridges_pkey RENAME TO host_agents_pkey")
    op.execute("ALTER INDEX bridges_host_id_key RENAME TO host_agents_host_id_key")

    # ── rename table back ──
    op.rename_table("bridges", "host_agents")
