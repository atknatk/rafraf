"""REST endpoints for session-level analytics (T2.5).

Currently exposes a single endpoint:

    GET /api/v1/sessions/cost-summary
        Aggregate per-user cost over a chosen period (current_month default,
        plus last_month / current_week / last_7_days). See
        ``app.schemas.sessions.SessionCostSummary`` for the response shape.

The data source is the ``sessions`` table populated by alembic 017 +
``ClaudeCodeRunner._dispatch_event`` (T2.5 wiring). This route does not
mutate state.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, get_args

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.repositories.session_repo import (
    CostPeriod,
    SessionRepository,
    resolve_period_window,
)
from app.schemas.sessions import (
    CostPeriodLiteral,
    SessionCostBreakdownItem,
    SessionCostSummary,
)

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])

# Server-side cap on how many breakdown rows the summary inlines. Most
# users never exceed a few hundred per month; we cap to avoid pathological
# response sizes when sessions are short-lived (e.g. CI runs spawning new
# sessions for every command). Clients can drop down to a future
# /sessions/cost-history endpoint when they need the long tail.
_MAX_BREAKDOWN_ROWS = 200

# Tuple form for FastAPI's enum-like Query validation.
_VALID_PERIODS: tuple[CostPeriod, ...] = get_args(CostPeriodLiteral)


@router.get("/cost-summary", response_model=SessionCostSummary)
async def get_cost_summary(
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    period: Annotated[
        CostPeriod,
        Query(
            description=(
                "Aggregation window. Defaults to current_month. Allowed: "
                "current_month, last_month, current_week, last_7_days."
            ),
        ),
    ] = "current_month",
) -> SessionCostSummary:
    """Aggregate per-session cost for the authenticated user.

    Implementation notes:
        * Period boundaries are resolved by ``resolve_period_window`` so the
          API surface matches the unit tests for that helper.
        * The DB filter is ``cost_updated_at >= start`` (and ``< end`` for
          windowed periods like ``last_month``); sessions that have never
          had cost recorded are excluded from the breakdown but still exist
          in the ``sessions`` table.
        * Aggregation happens in Python after fetch — the row count is
          capped by ``_MAX_BREAKDOWN_ROWS`` and the columns are NUMERIC so a
          few hundred Decimals is trivial overhead. If volume grows we can
          switch to a SQL GROUP BY without changing the response shape.
    """
    repo = SessionRepository(session)
    start, end, label = resolve_period_window(period)

    rows = await repo.list_costs_for_user_in_period(
        user_id=current_user.id,
        period_start=start,
        period_end=end,
    )

    total_cost = Decimal("0")
    total_input = 0
    total_output = 0
    total_cache_creation = 0
    total_cache_read = 0
    breakdown: list[SessionCostBreakdownItem] = []

    for row in rows:
        cost = row.total_cost_usd or Decimal("0")
        in_tok = row.total_input_tokens or 0
        out_tok = row.total_output_tokens or 0
        cache_create = row.total_cache_creation_tokens or 0
        cache_read = row.total_cache_read_tokens or 0

        total_cost += cost
        total_input += in_tok
        total_output += out_tok
        total_cache_creation += cache_create
        total_cache_read += cache_read

        if len(breakdown) < _MAX_BREAKDOWN_ROWS:
            breakdown.append(
                SessionCostBreakdownItem(
                    session_id=row.id,
                    cost_usd=cost,
                    started_at=row.started_at,
                    cost_updated_at=row.cost_updated_at,
                    total_input_tokens=in_tok,
                    total_output_tokens=out_tok,
                    total_tokens=(
                        in_tok + out_tok + cache_create + cache_read
                    ),
                )
            )

    return SessionCostSummary(
        period=label,
        period_kind=period,
        period_start=start,
        period_end=end,
        user_id=current_user.id,
        total_cost_usd=total_cost,
        session_count=len(rows),
        total_input_tokens=total_input,
        total_output_tokens=total_output,
        total_cache_creation_tokens=total_cache_creation,
        total_cache_read_tokens=total_cache_read,
        by_session=breakdown,
    )
