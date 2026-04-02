"""Oturum ve kullanim analitik servisi."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cost_log import CostLog
from app.models.message import Message

logger: structlog.stdlib.BoundLogger = structlog.get_logger()


class AnalyticsService:
    """Oturum ve kullanim analitiklerini hesaplar."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_project_analytics(
        self,
        user_id: str,
        project_id: uuid.UUID | None = None,
        days: int = 7,
    ) -> dict[str, object]:
        """Proje icin son N gunluk analitik ozeti dondurur."""
        since = datetime.now(tz=UTC) - timedelta(days=days)

        # Mesaj istatistikleri
        msg_stmt = select(
            Message.role,
            func.count(Message.id).label("msg_count"),
            func.sum(Message.tokens_used).label("total_tokens"),
        ).where(
            Message.user_id == user_id,
            Message.created_at >= since,
        )
        if project_id:
            msg_stmt = msg_stmt.where(Message.project_id == project_id)
        msg_stmt = msg_stmt.group_by(Message.role)

        msg_result = await self._session.execute(msg_stmt)
        msg_rows = msg_result.all()

        user_count = 0
        assistant_count = 0
        total_tokens = 0
        for row in msg_rows:
            if row.role == "user":
                user_count = int(row.msg_count)
            elif row.role == "assistant":
                assistant_count = int(row.msg_count)
            total_tokens += int(row.total_tokens or 0)

        # Model dagilimi
        model_stmt = select(
            Message.model_used,
            func.count(Message.id).label("model_count"),
        ).where(
            Message.user_id == user_id,
            Message.created_at >= since,
            Message.role == "assistant",
            Message.model_used.isnot(None),
        )
        if project_id:
            model_stmt = model_stmt.where(Message.project_id == project_id)
        model_stmt = model_stmt.group_by(Message.model_used)

        model_result = await self._session.execute(model_stmt)
        model_rows = model_result.all()
        model_distribution: dict[str, int] = {
            str(row.model_used): int(row.model_count) for row in model_rows
        }

        # Gunluk aktivite (son N gun)
        day_stmt = select(
            func.date_trunc("day", Message.created_at).label("day"),
            func.count(Message.id).label("day_count"),
        ).where(
            Message.user_id == user_id,
            Message.created_at >= since,
        )
        if project_id:
            day_stmt = day_stmt.where(Message.project_id == project_id)
        day_stmt = day_stmt.group_by(func.date_trunc("day", Message.created_at)).order_by(
            func.date_trunc("day", Message.created_at)
        )

        day_result = await self._session.execute(day_stmt)
        day_rows = day_result.all()
        daily_activity: list[dict[str, object]] = [
            {"date": str(row.day.date()), "count": int(row.day_count)} for row in day_rows
        ]

        # Maliyet ozeti — CostLog'da project_id yok, user bazinda filtrele
        cost_stmt = select(
            func.sum(CostLog.cost_usd).label("total_cost"),
            func.count(CostLog.id).label("cost_events"),
        ).where(
            CostLog.user_id == uuid.UUID(user_id),
            CostLog.called_at >= since,
        )

        cost_result = await self._session.execute(cost_stmt)
        cost_row = cost_result.one_or_none()
        total_cost = float(cost_row.total_cost or 0) if cost_row else 0.0
        cost_events = int(cost_row.cost_events or 0) if cost_row else 0

        logger.info(
            "project_analytics_computed",
            user_id=user_id,
            project_id=str(project_id) if project_id else None,
            days=days,
            total_messages=user_count + assistant_count,
            total_tokens=total_tokens,
            total_cost_usd=round(total_cost, 6),
        )

        return {
            "period_days": days,
            "since": since.isoformat(),
            "messages": {
                "user": user_count,
                "assistant": assistant_count,
                "total": user_count + assistant_count,
            },
            "tokens": {
                "total": total_tokens,
                "avg_per_response": (
                    round(total_tokens / assistant_count) if assistant_count > 0 else 0
                ),
            },
            "cost": {
                "total_usd": round(total_cost, 6),
                "events": cost_events,
                "avg_per_message_usd": (
                    round(total_cost / assistant_count, 6) if assistant_count > 0 else 0.0
                ),
            },
            "models": model_distribution,
            "daily_activity": daily_activity,
        }
