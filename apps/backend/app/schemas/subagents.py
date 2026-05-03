"""Pydantic schemas for the subagent REST hydration endpoint.

Owned by V1.x Item 9 — adds REST hydration for ``SubagentRepositoryImpl``
on iOS so app cold-start no longer drops subagent state until the bridge
re-emits.

Contract alignment (post-reviewer feedback)
-------------------------------------------
The response schema is **field-for-field aligned** with the iOS
``SubagentRestDTO`` declared in
``apps/ios/RafRaf/Features/Agent/Data/Repositories/SubagentRepositoryImpl.swift``
so the iOS mapper can fold REST and WS sources through the same code
path:

* ``id`` is the **bridge ``task_id``** (string), NOT the SQL primary key.
  iOS ``Subagent.id`` is documented as "Bridge task_id — subagent
  calismasinin benzersiz kimligi" (Subagent.swift:12-13). The WS push
  mapper feeds ``id: content.taskId``; if REST sent the SQL UUID
  instead, ``SubagentRepositoryImpl.SubagentState.mergeIfAbsent`` would
  key the same logical row twice → duplicate timeline entries on the
  next live update. ``db_id`` is exposed as a separate field for any
  caller that genuinely needs the SQL primary key.
* ``summary`` (NOT ``output_summary``) — iOS decodes ``summary`` directly.
* All metadata + accounting fields (``name``, ``subagent_type``,
  ``prompt_preview``, ``isolation``, ``total_tokens``, ``tool_uses``,
  ``duration_ms``, ``updated_at``) are exposed even when null so iOS
  rendering stays uniform across REST hydration and WS push paths.
* ``activity`` and ``progress_percent`` are NOT persisted (the bridge
  derives them from ``system/task_progress`` events that are rare and
  ephemeral) → always null on REST hydration. iOS treats null as "no
  in-flight progress information" and falls back to live WS for the
  detail.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Allowed lifecycle status values — mirrors the bridge's
# ``SubagentState.Status`` enum (apps/rafraf-bridge/internal/claude/state.go)
# and the ``status`` column default declared in alembic 016. Kept open as a
# Literal (not an enum) so a future bridge schema can append values without
# breaking iOS — the service still coerces unknowns and emits a warning so
# the drift is observable.
SubagentStatusLiteral = Literal["spawned", "in_progress", "completed", "failed"]


class SubagentResponse(BaseModel):
    """REST hydration row for one subagent recorded in a claude session.

    Frozen so the route assembles the DTO once and never mutates it after
    construction (consistent with ``SessionCostBreakdownItem``).

    JSON keys are snake_case; iOS decodes via ``NetworkClient`` snake_case
    -> camelCase auto-conversion (see ``SubagentRestDTO``).
    """

    model_config = ConfigDict(frozen=True)

    # ── identity ──
    # Bridge task_id — the canonical iOS identity for a subagent.
    id: str = Field(
        description=(
            "Bridge ``task_id`` — the canonical subagent identity used "
            "by iOS as the primary cache key. Matches the WS push "
            "``content.task_id`` so REST hydration and WS updates merge "
            "into the same row."
        ),
    )
    # SQL primary key — exposed as a separate field for any caller that
    # needs it (e.g. backend admin tooling). iOS ignores ``db_id``.
    db_id: uuid.UUID = Field(
        description=(
            "Server-side SQL primary key from the ``subagents`` table. "
            "Distinct from ``id`` (which is the bridge task_id). Backend "
            "admin / debugging only — iOS does not consume this field."
        ),
    )
    parent_id: str | None = Field(
        default=None,
        description=(
            "Orchestrator (parent) claude session id when known by the "
            "bridge, otherwise null. Maps to the model column "
            "``parent_session_id``."
        ),
    )
    session_id: str = Field(
        description="Claude session id this subagent ran inside.",
    )

    # ── lifecycle ──
    status: SubagentStatusLiteral = Field(
        description="Current lifecycle status: spawned / in_progress / completed / failed.",
    )

    # ── descriptive metadata (from system/task_started) ──
    name: str | None = Field(
        default=None,
        description="Short subagent label (e.g. 'developer', 'tester'). May be null.",
    )
    description: str | None = Field(
        default=None,
        description="Long-form description supplied at spawn time. May be null.",
    )
    prompt_preview: str | None = Field(
        default=None,
        description="Truncated preview of the spawn prompt (~200 chars). May be null.",
    )
    subagent_type: str | None = Field(
        default=None,
        description="Bridge subagent_type label (e.g. 'general-purpose'). May be null.",
    )
    isolation: str | None = Field(
        default=None,
        description="'worktree' if the subagent runs in an isolated worktree, otherwise null.",
    )

    # ── progress (live-only — not persisted) ──
    activity: str | None = Field(
        default=None,
        description=(
            "Short in-flight activity label (e.g. 'Editing config.toml'). "
            "Always null on REST hydration today — the CLI rarely emits "
            "``system/task_progress`` and the column is not persisted. "
            "iOS receives the live value via WS ``subagent.progress``."
        ),
    )
    progress_percent: int | None = Field(
        default=None,
        ge=0,
        le=100,
        description=(
            "Best-effort progress hint (0..100). Always null on REST "
            "hydration today — not persisted. iOS treats null as 'no "
            "progress information'."
        ),
    )

    # ── terminal payload (from system/task_notification) ──
    summary: str | None = Field(
        default=None,
        description=(
            "Terminal summary text from ``system/task_notification``. "
            "JSON key matches iOS ``SubagentRestDTO.summary`` (NOT "
            "``output_summary``)."
        ),
    )
    total_tokens: int | None = Field(
        default=None,
        ge=0,
        description="Total tokens consumed by the subagent. Null until completion.",
    )
    tool_uses: int | None = Field(
        default=None,
        ge=0,
        description="Number of tool invocations the subagent made. Null until completion.",
    )
    duration_ms: int | None = Field(
        default=None,
        ge=0,
        description="Wall-clock duration in milliseconds. Null until completion.",
    )

    # ── timestamps ──
    started_at: datetime = Field(
        description="When the bridge observed the spawn (UTC). Maps to model.spawned_at.",
    )
    updated_at: datetime | None = Field(
        default=None,
        description="Last in-flight progress mutation (UTC), or null if no updates seen.",
    )
    completed_at: datetime | None = Field(
        default=None,
        description="When the bridge observed termination (UTC), or null if still running.",
    )
