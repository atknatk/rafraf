"""Add bridge ``permission_request`` correlation fields to approval_requests (V1.4).

Revision ID: 018_approval_permission_request
Revises: 017_session_cost_tracking
Create Date: 2026-05-02

Per RafRaf V1 permission-blocker design (``docs/design/v1-permission-blockers.md``
V1.4 §2.1.4 + §2.2.3) the backend orchestrator receives a new envelope —
``event.session.permission_request`` — emitted by the bridge whenever the
PreToolUse hook intercepts a tool call. Each bridge envelope carries:

* ``request_id`` — bridge-generated UUID, the decision correlation token
  the bridge's UDS broker (``apps/rafraf-bridge/internal/permission/``)
  uses to resolve the open hook UDS connection. We MUST persist this so a
  late-arriving decision (e.g. backend restart mid-flight) can still be
  routed back to the right broker waiter via the eventual replay path.
* ``bridge_host_id`` — the host that emitted the envelope, needed by the
  backend's ``_await_and_dispatch_decision`` helper to know where to send
  the ``command.claude.permission.{allow,deny}`` envelope back.
* ``rpc_id`` — the outer envelope's ``correlation_id`` (= the originating
  ``command.claude.run`` rpc id). The bridge's inbound dispatcher echoes
  this on the decision RPC so the bridge-side runner can route the reply
  to the correct broker invocation. Persisting it lets us reconstruct the
  routing trio (host, rpc, request) from the audit log without joining
  against ephemeral in-memory state.
* ``timeout_seconds`` — the bridge-suggested deadline (default 30 s,
  honoured by iOS RFApprovalSheet's countdown). When the field is NULL we
  fall back to ``CATEGORY_TIMEOUTS`` (180 s WRITE_REMOTE / 300 s others).

All four columns are nullable so legacy in-app approvals (the
orchestrator-mediated path the V1 design's §1.2 documents) keep working
without back-fill — only bridge-originated rows populate them.

Migration chain note
--------------------
``down_revision`` is **017_session_cost_tracking** (T2.5 — currently the
linear head). Pure additive change (4 nullable columns), no index
required: lookups happen by primary key (``id``) which already has the
implicit unique index from ``UUIDMixin``.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "018_approval_permission_request"
down_revision: str | None = "017_session_cost_tracking"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add 4 nullable bridge-correlation columns to ``approval_requests``."""
    op.add_column(
        "approval_requests",
        sa.Column("request_id", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "approval_requests",
        sa.Column("bridge_host_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "approval_requests",
        sa.Column("rpc_id", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "approval_requests",
        sa.Column("bridge_timeout_seconds", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    """Drop the 4 V1.4 columns. Reverse-order to match ``upgrade``."""
    op.drop_column("approval_requests", "bridge_timeout_seconds")
    op.drop_column("approval_requests", "rpc_id")
    op.drop_column("approval_requests", "bridge_host_id")
    op.drop_column("approval_requests", "request_id")
