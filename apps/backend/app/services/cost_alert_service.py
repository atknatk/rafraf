"""Maliyet bütçe eşiği takip ve uyarı servisi.

Kullanıcı veya proje bazında günlük/aylık maliyet eşiği kontrolü yapar.
Eşik aşıldığında bildirim gönderir.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cost_log import CostLog

logger: structlog.stdlib.BoundLogger = structlog.get_logger()


class CostPeriod:
    """Maliyet hesaplama dönemleri."""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class CostAlertService:
    """Kullanıcı maliyetlerini hesaplar ve bütçe eşiklerini kontrol eder."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_cost_summary(
        self,
        user_id: str,
        period: str = CostPeriod.DAILY,
        project_id: str | None = None,  # noqa: ARG002 — future use when cost_logs has project_id
    ) -> dict[str, object]:
        """Belirtilen dönem için maliyet özeti döndürür.

        Args:
            user_id: Kullanıcı UUID string
            period: "daily" | "weekly" | "monthly"
            project_id: Opsiyonel proje filtresi (henüz cost_logs'da yok)

        Returns:
            cost_usd, token_count, call_count, period, threshold_pct içeren dict
        """
        uid = uuid.UUID(user_id)
        since = self._period_start(period)

        stmt = select(
            func.sum(CostLog.cost_usd).label("total_cost"),
            func.sum(CostLog.total_tokens).label("total_tokens"),
            func.count(CostLog.id).label("call_count"),
        ).where(
            CostLog.user_id == uid,
            CostLog.called_at >= since,
        )
        result = await self._session.execute(stmt)
        row = result.one()

        total_cost: float = float(row.total_cost or 0.0)
        total_tokens: int = int(row.total_tokens or 0)
        call_count: int = int(row.call_count or 0)

        return {
            "user_id": user_id,
            "period": period,
            "since": since.isoformat(),
            "cost_usd": round(total_cost, 6),
            "token_count": total_tokens,
            "call_count": call_count,
        }

    async def check_budget(
        self,
        user_id: str,
        budget_usd: float,
        period: str = CostPeriod.DAILY,
    ) -> dict[str, object]:
        """Kullanıcının bütçe eşiğine ne kadar yaklaştığını kontrol eder.

        Returns:
            exceeded: bool, usage_pct: float, remaining_usd: float
        """
        summary = await self.get_cost_summary(user_id=user_id, period=period)
        cost_usd = float(summary["cost_usd"])  # type: ignore[arg-type]
        usage_pct = (cost_usd / budget_usd * 100) if budget_usd > 0 else 0.0
        remaining = max(0.0, budget_usd - cost_usd)
        exceeded = cost_usd >= budget_usd

        await logger.ainfo(
            "budget_check",
            user_id=user_id,
            period=period,
            cost_usd=cost_usd,
            budget_usd=budget_usd,
            usage_pct=round(usage_pct, 1),
            exceeded=exceeded,
        )

        return {
            "user_id": user_id,
            "period": period,
            "budget_usd": budget_usd,
            "cost_usd": cost_usd,
            "remaining_usd": round(remaining, 6),
            "usage_pct": round(usage_pct, 1),
            "exceeded": exceeded,
            "warning": usage_pct >= 80 and not exceeded,
        }

    async def get_top_models_by_cost(
        self,
        user_id: str,
        period: str = CostPeriod.MONTHLY,
        limit: int = 5,
    ) -> list[dict[str, object]]:
        """Maliyet bazında en çok kullanılan modelleri döndürür."""
        uid = uuid.UUID(user_id)
        since = self._period_start(period)

        stmt = (
            select(
                CostLog.model,
                func.sum(CostLog.cost_usd).label("cost"),
                func.sum(CostLog.total_tokens).label("tokens"),
                func.count(CostLog.id).label("calls"),
            )
            .where(CostLog.user_id == uid, CostLog.called_at >= since)
            .group_by(CostLog.model)
            .order_by(func.sum(CostLog.cost_usd).desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)

        return [
            {
                "model": row.model,
                "cost_usd": round(float(row.cost or 0), 6),
                "token_count": int(row.tokens or 0),
                "call_count": int(row.calls or 0),
            }
            for row in result
        ]

    async def get_daily_cost_trend(
        self,
        user_id: str,
        days: int = 30,
    ) -> list[dict[str, object]]:
        """Son N günlük günlük maliyet trendini döndürür."""
        uid = uuid.UUID(user_id)
        since = datetime.now(tz=UTC) - timedelta(days=days)

        stmt = (
            select(
                func.date_trunc("day", CostLog.called_at).label("day"),
                func.sum(CostLog.cost_usd).label("cost"),
                func.sum(CostLog.total_tokens).label("tokens"),
            )
            .where(CostLog.user_id == uid, CostLog.called_at >= since)
            .group_by(func.date_trunc("day", CostLog.called_at))
            .order_by(func.date_trunc("day", CostLog.called_at))
        )
        result = await self._session.execute(stmt)

        return [
            {
                "date": row.day.date().isoformat() if row.day else None,
                "cost_usd": round(float(row.cost or 0), 6),
                "token_count": int(row.tokens or 0),
            }
            for row in result
        ]

    @staticmethod
    def _period_start(period: str) -> datetime:
        """Dönem başlangıç zamanını döndürür."""
        now = datetime.now(tz=UTC)
        if period == CostPeriod.DAILY:
            return now.replace(hour=0, minute=0, second=0, microsecond=0)
        if period == CostPeriod.WEEKLY:
            days_since_monday = now.weekday()
            return (now - timedelta(days=days_since_monday)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
        # monthly
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
