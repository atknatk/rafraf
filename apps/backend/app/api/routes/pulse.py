"""Pulse API routes — günlük AI proje özeti endpoint'leri."""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.pulse import PulseNotAvailableResponse, PulseReportResponse
from app.services.pulse_service import PulseService, get_pulse_service

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/pulse", tags=["pulse"])


def _to_response(pulse: object) -> PulseReportResponse:
    """PulseReport SQLAlchemy modelini PulseReportResponse'a dönüştürür."""
    from app.models.pulse_report import PulseReport

    p: PulseReport = pulse  # type: ignore[assignment]
    return PulseReportResponse(
        id=str(p.id),
        report_date=p.report_date.isoformat(),
        period_start=p.period_start.isoformat(),
        period_end=p.period_end.isoformat(),
        total_messages=p.total_messages,
        user_messages=p.user_messages,
        assistant_messages=p.assistant_messages,
        total_cost_usd=p.total_cost_usd,
        models_used=p.models_used,
        summary_text=p.summary_text,
        completed_items=p.completed_items,
        in_progress_items=p.in_progress_items,
        risks=p.risks,
        suggestions=p.suggestions,
        generated_at=p.created_at.isoformat(),
    )


@router.get(
    "/latest",
    response_model=PulseReportResponse | PulseNotAvailableResponse,
    summary="En güncel pulse report'u döndürür",
)
async def get_latest_pulse(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    svc: Annotated[PulseService, Depends(get_pulse_service)],
    project_id: str | None = None,
) -> PulseReportResponse | PulseNotAvailableResponse:
    """En güncel pulse raporunu döndürür.

    Rapor yoksa `PulseNotAvailableResponse` ile 200 döner.
    """
    pulse = await svc.get_latest_pulse(db, project_id=project_id)
    if pulse is None:
        logger.info(
            "pulse_not_available",
            project_id=project_id,
            user_id=str(current_user.id),
        )
        return PulseNotAvailableResponse(
            message="Henüz pulse raporu yok",
            next_generation_at=PulseService.next_generation_at(),
        )

    logger.info(
        "pulse_returned",
        pulse_id=str(pulse.id),
        user_id=str(current_user.id),
    )
    return _to_response(pulse)


@router.post(
    "/generate",
    status_code=202,
    summary="Pulse raporu manuel olarak tetikler (test için)",
)
async def trigger_pulse_generation(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    svc: Annotated[PulseService, Depends(get_pulse_service)],
    project_id: str | None = None,
    days: int = 1,
) -> dict[str, str]:
    """Pulse raporu üretimini manuel tetikler.

    Arka planda hemen üretip kayıt ID'sini döner.
    """
    pulse = await svc.generate_pulse(
        db,
        project_id=project_id,
        user_id=current_user.id,
        days=days,
    )
    logger.info(
        "pulse_generated",
        pulse_id=str(pulse.id),
        user_id=str(current_user.id),
        project_id=project_id,
    )
    return {"pulse_id": str(pulse.id), "status": "generated"}
