"""Drop legacy ``dangerously_skip_permissions`` column from ``bridges``.

Revision ID: 015_drop_legacy_bridge_columns
Revises: 014_rename_host_agents_bridges
Create Date: 2026-05-02

Per RafRaf V1 production pivot (docs/10 §6.1.1) the Go bridge runner
contract no longer carries ``dangerously_skip_permissions`` as a per-bridge
setting — it is now a per-invocation parameter (``permission_mode``) on
the ``claude.runner`` subprocess wrapper. T1.3 drops the dead column from
the schema, the ORM model, the Pydantic schemas, the ``BridgeRepository``,
and the related ``BridgeRegistryService`` plumbing in one atomic change.

Coordination note for T1.10
---------------------------
T1.10 owns the next alembic migration (subagents projection). To avoid a
revision-number collision this migration uses revision ``015`` and T1.10
should use revision ``016`` (or later). The down_revision chain stays
linear: 013 → 014 → 015 → (T1.10's 016).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "015_drop_legacy_bridge_columns"
down_revision: str | None = "014_rename_host_agents_bridges"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop ``dangerously_skip_permissions`` from ``bridges``."""
    op.drop_column("bridges", "dangerously_skip_permissions")


def downgrade() -> None:
    """Re-add ``dangerously_skip_permissions`` to ``bridges`` with the original default."""
    op.add_column(
        "bridges",
        sa.Column(
            "dangerously_skip_permissions",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
