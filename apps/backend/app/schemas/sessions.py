"""Pydantic schemas for the ``GET /api/v1/sessions/cost-summary`` endpoint.

Owned by T2.5 (RafRaf Faz 2 — Production Hardening, see
docs/10_Production_Pivot_Spec.md §8 Faz 2 and
docs/12_Action_Plan_Tasks.md §6). The endpoint exposes the per-session
cost columns added by alembic 017 in an aggregate-then-breakdown shape so
clients can render both a "total spend this month" headline and a
drill-down table without follow-up requests.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Period vocabulary — kept in sync with
# ``app.repositories.session_repo.CostPeriod``. Duplicated here (rather
# than re-exported) so the schema layer stays decoupled from the repo.
CostPeriodLiteral = Literal["current_month", "last_month", "current_week", "last_7_days"]


class SessionCostBreakdownItem(BaseModel):
    """One row in the per-session cost breakdown.

    ``cost_usd`` is rendered as a string at the JSON boundary by Pydantic's
    default ``Decimal`` serializer to preserve precision (the column is
    ``NUMERIC(10, 6)``); clients should parse it as a high-precision
    decimal rather than a 64-bit float.

    T2.5 M3: ``frozen=True`` so the DTO is immutable once constructed —
    the endpoint builds the row in one place and never mutates it
    afterwards. Pydantic raises ``ValidationError`` on attribute assignment.
    """

    model_config = ConfigDict(frozen=True)

    session_id: uuid.UUID = Field(description="Sessions table primary key.")
    cost_usd: Decimal = Field(
        description="Cumulative cost recorded against this session.",
    )
    started_at: datetime = Field(description="Session start timestamp (UTC).")
    cost_updated_at: datetime | None = Field(
        default=None,
        description="Last time a cost increment was persisted (UTC).",
    )
    total_input_tokens: int = Field(
        default=0,
        ge=0,
        description="Sum of per-model input_tokens across the session.",
    )
    total_output_tokens: int = Field(
        default=0,
        ge=0,
        description="Sum of per-model output_tokens across the session.",
    )
    total_tokens: int = Field(
        default=0,
        ge=0,
        description=("Convenience sum: input + output + cache_creation + cache_read."),
    )


class SessionCostSummary(BaseModel):
    """Top-level response for ``GET /api/v1/sessions/cost-summary``.

    ``period`` is the canonical label for the requested window — e.g.
    ``"2026-05"`` for current_month, ``"2026-W18"`` for current_week,
    ``"last_7_days"`` for the rolling-window variant. Clients should treat
    it as opaque (suitable for display, not for parsing).

    T2.5 M3: ``frozen=True`` so the response DTO is immutable once
    constructed in the route. The endpoint computes totals in local
    accumulators and assembles the model in a single ``return`` — there
    is no post-construction mutation in the call path.
    """

    model_config = ConfigDict(frozen=True)

    period: str = Field(
        description="Canonical label for the period (display only).",
    )
    period_kind: CostPeriodLiteral = Field(
        description="Echo of the requested period query parameter.",
    )
    period_start: datetime = Field(description="Inclusive UTC window start.")
    period_end: datetime | None = Field(
        default=None,
        description="Exclusive UTC window end; null when window flows to now.",
    )
    user_id: uuid.UUID = Field(description="User the summary is scoped to.")
    total_cost_usd: Decimal = Field(
        description="Sum of cost_usd across the breakdown rows.",
    )
    session_count: int = Field(
        ge=0,
        description="Number of sessions contributing to total_cost_usd.",
    )
    total_input_tokens: int = Field(ge=0)
    total_output_tokens: int = Field(ge=0)
    total_cache_creation_tokens: int = Field(ge=0)
    total_cache_read_tokens: int = Field(ge=0)
    by_session: list[SessionCostBreakdownItem] = Field(
        default_factory=list,
        description=(
            "Per-session breakdown ordered by cost_updated_at DESC. "
            "Capped server-side (see endpoint docstring)."
        ),
    )
