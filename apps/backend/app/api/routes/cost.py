"""REST endpoints for cost tracker (token usage, reports, budget alerts)."""

import uuid
from datetime import date
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.api.deps import get_db
from app.repositories.cost_repository import CostRepository
from app.schemas.cost import (
    BudgetStatusResponse,
    CostLogCreateRequest,
    CostLogListResponse,
    CostLogResponse,
    CostReportResponse,
    UserCostSummaryResponse,
)
from app.services.cost_service import cost_service

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/cost", tags=["cost"])


# --- Cost Log Endpoints ---


@router.post(
    "/log",
    response_model=CostLogResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_cost_log(
    body: CostLogCreateRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> CostLogResponse:
    """Record a new AI API call cost entry.

    Calculates cost automatically based on model pricing and token counts.
    """
    repo = CostRepository(session)
    entity = await cost_service.record_usage(
        repo,
        user_id=body.user_id,
        model=body.model,
        input_tokens=body.input_tokens,
        output_tokens=body.output_tokens,
        session_id=body.session_id,
        tool_name=body.tool_name,
    )
    return CostLogResponse(
        id=entity.id,
        user_id=entity.user_id,
        model=entity.model,
        input_tokens=entity.input_tokens,
        output_tokens=entity.output_tokens,
        total_tokens=entity.total_tokens,
        cost_usd=entity.cost_usd,
        session_id=entity.session_id,
        tool_name=entity.tool_name,
        called_at=entity.called_at,
        created_at=entity.created_at,
    )


@router.get("/logs/{user_id}", response_model=CostLogListResponse)
async def list_user_cost_logs(
    user_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100, description="Sayfa basi sonuc")] = 50,
    offset: Annotated[int, Query(ge=0, description="Atlama miktari")] = 0,
) -> CostLogListResponse:
    """List cost log entries for a user with pagination."""
    repo = CostRepository(session)
    items, total = await cost_service.get_user_logs(repo, user_id, limit=limit, offset=offset)
    return CostLogListResponse(items=items, total=total)


# --- Report Endpoints ---


@router.get("/report", response_model=CostReportResponse)
async def get_cost_report(
    session: Annotated[AsyncSession, Depends(get_db)],
    period: Annotated[
        str, Query(pattern="^(daily|monthly)$", description="Rapor periyodu")
    ] = "daily",
    target_date: Annotated[date | None, Query(description="Rapor tarihi (YYYY-MM-DD)")] = None,
    user_id: Annotated[uuid.UUID | None, Query(description="Kullanici filtresi")] = None,
) -> CostReportResponse:
    """Generate a daily or monthly cost report with model breakdown."""
    repo = CostRepository(session)
    return await cost_service.generate_report(
        repo,
        period=period,
        target_date=target_date,
        user_id=user_id,
    )


@router.get("/users", response_model=list[UserCostSummaryResponse])
async def get_user_cost_summaries(
    session: Annotated[AsyncSession, Depends(get_db)],
    start_date: Annotated[date | None, Query(description="Baslangic tarihi")] = None,
    end_date: Annotated[date | None, Query(description="Bitis tarihi")] = None,
) -> list[UserCostSummaryResponse]:
    """Get per-user cost summaries for a date range."""
    repo = CostRepository(session)
    return await cost_service.get_user_summaries(
        repo,
        start_date=start_date,
        end_date=end_date,
    )


# --- Budget Endpoints ---


@router.get("/budget", response_model=BudgetStatusResponse)
async def get_budget_status(
    session: Annotated[AsyncSession, Depends(get_db)],
    user_id: Annotated[uuid.UUID | None, Query(description="Kullanici filtresi")] = None,
    daily_limit_usd: Annotated[
        float | None, Query(ge=0.0, description="Gunluk limit (USD)")
    ] = None,
    monthly_limit_usd: Annotated[
        float | None, Query(ge=0.0, description="Aylik limit (USD)")
    ] = None,
) -> BudgetStatusResponse:
    """Check current budget status and alert flags."""
    repo = CostRepository(session)
    return await cost_service.get_budget_status(
        repo,
        user_id=user_id,
        daily_limit_usd=daily_limit_usd,
        monthly_limit_usd=monthly_limit_usd,
    )


# --- Model Pricing Endpoint ---


@router.get("/models")
async def list_supported_models() -> list[dict[str, object]]:
    """List supported AI models and their pricing."""
    return cost_service.get_supported_models()
