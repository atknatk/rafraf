"""Analitik API endpoint'leri."""

from __future__ import annotations

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.services.analytics_service import AnalyticsService

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


@router.get("/project")
async def get_project_analytics(
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    project_id: Annotated[
        uuid.UUID | None,
        Query(description="Proje ID'si"),
    ] = None,
    days: Annotated[
        int,
        Query(ge=1, le=90, description="Kac gunluk veri"),
    ] = 7,
) -> dict[str, object]:
    """Proje analitik ozetini dondurur (mesaj sayisi, token, maliyet, gunluk aktivite)."""
    svc = AnalyticsService(session)
    return await svc.get_project_analytics(
        user_id=str(current_user.id),
        project_id=project_id,
        days=days,
    )
