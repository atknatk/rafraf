"""Maliyet uyarı ve bütçe kontrol endpoint'leri."""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.services.cost_alert_service import CostAlertService, CostPeriod

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/costs", tags=["costs"])


@router.get("/summary")
async def get_cost_summary(
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    period: Annotated[
        str,
        Query(description="Dönem: daily | weekly | monthly"),
    ] = CostPeriod.DAILY,
) -> dict[str, object]:
    """Belirtilen dönem için maliyet özeti."""
    svc = CostAlertService(session)
    return await svc.get_cost_summary(user_id=str(current_user.id), period=period)


@router.get("/budget-check")
async def check_budget(
    budget_usd: Annotated[
        float,
        Query(gt=0, description="Bütçe eşiği (USD)"),
    ],
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    period: Annotated[
        str,
        Query(description="Dönem: daily | weekly | monthly"),
    ] = CostPeriod.DAILY,
) -> dict[str, object]:
    """Bütçe eşiğine göre kullanım durumunu kontrol et.

    Döndürülen `exceeded: true` ise eşik aşılmış.
    `warning: true` ise %80 veya üzerinde.
    """
    svc = CostAlertService(session)
    return await svc.check_budget(
        user_id=str(current_user.id),
        budget_usd=budget_usd,
        period=period,
    )


@router.get("/top-models")
async def get_top_models_by_cost(
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    period: Annotated[
        str,
        Query(description="Dönem: daily | weekly | monthly"),
    ] = CostPeriod.MONTHLY,
    limit: Annotated[
        int,
        Query(ge=1, le=20, description="Maksimum model sayısı"),
    ] = 5,
) -> list[dict[str, object]]:
    """Maliyet bazında en çok kullanılan modeller."""
    svc = CostAlertService(session)
    return await svc.get_top_models_by_cost(
        user_id=str(current_user.id),
        period=period,
        limit=limit,
    )


@router.get("/trend")
async def get_daily_cost_trend(
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    days: Annotated[
        int,
        Query(ge=1, le=90, description="Kaç günlük trend"),
    ] = 30,
) -> list[dict[str, object]]:
    """Son N günlük günlük maliyet trendi."""
    svc = CostAlertService(session)
    return await svc.get_daily_cost_trend(
        user_id=str(current_user.id),
        days=days,
    )
