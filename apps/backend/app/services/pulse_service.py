"""Pulse Service — günlük AI proje özeti oluşturma ve sorgulama."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

import anthropic
import structlog
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.cost_log import CostLog
from app.models.message import Message
from app.models.pulse_report import PulseReport

logger: structlog.stdlib.BoundLogger = structlog.get_logger()


class PulseService:
    """Günlük AI proje özetlerini üretir ve sorgular."""

    def __init__(self) -> None:
        settings = get_settings()
        api_key = settings.anthropic_api_key or None
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._haiku_model = settings.claude_simple_model

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    async def generate_pulse(
        self,
        db: AsyncSession,
        project_id: str | None = None,
        user_id: uuid.UUID | None = None,
        days: int = 1,
    ) -> PulseReport:
        """Son `days` günün aktivitesini analiz edip PulseReport üretir ve kaydeder.

        Args:
            db: Async DB oturumu.
            project_id: Proje filtresi (None → tüm projeler).
            user_id: Raporu tetikleyen kullanıcı (None → sistem UUID kullanılır).
            days: Kaç günlük aktivite analiz edilecek.

        Returns:
            Kaydedilmiş PulseReport örneği.
        """
        now = datetime.now(tz=UTC)
        period_end = now
        period_start = now - timedelta(days=days)
        report_date = now.date()

        effective_user_id: uuid.UUID = user_id or uuid.UUID(int=0)

        # 1. Mesajları çek
        messages = await self._fetch_messages(db, project_id, period_start, period_end)

        # 2. Maliyet loglarını çek
        costs = await self._fetch_costs(db, period_start, period_end)

        # 3. İstatistikleri hesapla
        total_messages = len(messages)
        user_messages = sum(1 for m in messages if m.role == "user")
        assistant_messages = sum(1 for m in messages if m.role == "assistant")
        total_cost_usd: float | None = sum(c.cost_usd for c in costs) if costs else None

        models_raw: set[str] = set()
        for m in messages:
            if m.model_used:
                models_raw.add(m.model_used)
        for c in costs:
            models_raw.add(c.model)
        models_used = sorted(models_raw)

        # 4. AI özeti üret
        summary_text, completed, in_progress, risks, suggestions = (
            await self._generate_ai_summary(messages, total_messages, total_cost_usd)
        )

        # 5. Kayıt oluştur
        pulse = PulseReport(
            project_id=uuid.UUID(project_id) if project_id else None,
            user_id=effective_user_id,
            report_date=report_date,
            period_start=period_start,
            period_end=period_end,
            total_messages=total_messages,
            user_messages=user_messages,
            assistant_messages=assistant_messages,
            total_cost_usd=total_cost_usd,
            models_used=models_used,
            summary_text=summary_text,
            completed_items=completed,
            in_progress_items=in_progress,
            risks=risks,
            suggestions=suggestions,
            raw_stats={
                "cost_entries": len(costs),
                "period_hours": days * 24,
            },
        )
        db.add(pulse)
        await db.commit()
        await db.refresh(pulse)

        log = logger.bind(
            project_id=project_id,
            total_messages=total_messages,
            report_date=str(report_date),
        )
        log.info("pulse_report_generated")
        return pulse

    async def get_latest_pulse(
        self,
        db: AsyncSession,
        project_id: str | None = None,
    ) -> PulseReport | None:
        """En güncel pulse report'u döndürür.

        Args:
            db: Async DB oturumu.
            project_id: Proje filtresi (None → proje bağımsız).

        Returns:
            En son PulseReport ya da None.
        """
        stmt = select(PulseReport).order_by(desc(PulseReport.created_at))

        if project_id is not None:
            stmt = stmt.where(
                PulseReport.project_id == uuid.UUID(project_id)
            )
        else:
            stmt = stmt.where(PulseReport.project_id.is_(None))

        result = await db.execute(stmt.limit(1))
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------ #
    #  Private helpers                                                     #
    # ------------------------------------------------------------------ #

    async def _fetch_messages(
        self,
        db: AsyncSession,
        project_id: str | None,
        period_start: datetime,
        period_end: datetime,
    ) -> list[Message]:
        stmt = (
            select(Message)
            .where(Message.created_at >= period_start)
            .where(Message.created_at <= period_end)
            .order_by(Message.created_at)
        )
        if project_id is not None:
            stmt = stmt.where(Message.project_id == uuid.UUID(project_id))

        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def _fetch_costs(
        self,
        db: AsyncSession,
        period_start: datetime,
        period_end: datetime,
    ) -> list[CostLog]:
        stmt = (
            select(CostLog)
            .where(CostLog.called_at >= period_start)
            .where(CostLog.called_at <= period_end)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def _generate_ai_summary(
        self,
        messages: list[Message],
        total_messages: int,
        total_cost_usd: float | None,
    ) -> tuple[str, list[str], list[str], list[str], list[str]]:
        """Claude Haiku ile AI özeti üretir.

        Hata durumunda istatistik tabanlı fallback döndürür.

        Returns:
            (summary_text, completed, in_progress, risks, suggestions) tuple.
        """
        fallback = self._build_fallback_summary(total_messages, total_cost_usd)

        if total_messages == 0:
            return fallback

        # Son 10 mesajı özetle
        sample_messages = messages[-10:]
        sample_text = "\n".join(
            f"[{m.role}]: {m.content[:200]}" for m in sample_messages
        )

        cost_info = f"{total_cost_usd:.4f} USD" if total_cost_usd is not None else "bilinmiyor"
        user_prompt = (
            f"Son periyotta {total_messages} mesaj işlendi. "
            f"Toplam maliyet: {cost_info}.\n\n"
            f"Son mesaj örnekleri:\n{sample_text}\n\n"
            "Lütfen aşağıdaki JSON formatında yanıt ver:\n"
            '{"summary": "kısa genel özet", '
            '"completed": ["tamamlanan madde 1"], '
            '"in_progress": ["devam eden madde 1"], '
            '"risks": ["risk 1"], '
            '"suggestions": ["öneri 1"]}'
        )

        try:
            response = await self._client.messages.create(
                model=self._haiku_model,
                max_tokens=300,
                system=(
                    "Sen bir AI proje asistanısın. "
                    "Proje aktivitelerini analiz et ve kısa, yapılandırılmış Türkçe özet üret. "
                    "Sadece geçerli JSON döndür, başka hiçbir şey ekleme."
                ),
                messages=[{"role": "user", "content": user_prompt}],
            )

            content = response.content[0]
            if content.type != "text":
                logger.warning("pulse_ai_unexpected_content_type", content_type=content.type)
                return fallback

            raw_text = content.text.strip()
            # JSON blok varsa çıkar
            if "```" in raw_text:
                raw_text = raw_text.split("```")[1]
                if raw_text.startswith("json"):
                    raw_text = raw_text[4:]

            parsed: dict[str, object] = json.loads(raw_text)
            summary_text = str(parsed.get("summary", ""))
            completed_raw = parsed.get("completed", [])
            completed: list[str] = (
                [str(x) for x in completed_raw] if isinstance(completed_raw, list) else []
            )
            in_progress_raw = parsed.get("in_progress", [])
            in_progress: list[str] = (
                [str(x) for x in in_progress_raw] if isinstance(in_progress_raw, list) else []
            )
            risks_raw = parsed.get("risks", [])
            risks: list[str] = (
                [str(x) for x in risks_raw] if isinstance(risks_raw, list) else []
            )
            suggestions_raw = parsed.get("suggestions", [])
            suggestions: list[str] = (
                [str(x) for x in suggestions_raw] if isinstance(suggestions_raw, list) else []
            )

            logger.info("pulse_ai_summary_generated", summary_len=len(summary_text))
            return summary_text, completed, in_progress, risks, suggestions

        except (json.JSONDecodeError, KeyError, IndexError, anthropic.APIError) as exc:
            logger.warning("pulse_ai_summary_failed", exc_info=exc)
            return fallback

    def _build_fallback_summary(
        self,
        total_messages: int,
        total_cost_usd: float | None,
    ) -> tuple[str, list[str], list[str], list[str], list[str]]:
        """AI çağrısı başarısız olursa istatistik tabanlı özet döndürür."""
        cost_text = f"{total_cost_usd:.4f} USD" if total_cost_usd is not None else "bilinmiyor"
        summary = f"Son periyotta {total_messages} mesaj işlendi. Toplam maliyet: {cost_text}."
        return summary, [], [], [], []

    # ------------------------------------------------------------------ #
    #  Raporlama tarihi yardımcısı                                        #
    # ------------------------------------------------------------------ #

    @staticmethod
    def next_generation_at() -> str:
        """Bir sonraki sabah 08:00 UTC zamanını ISO string olarak döndürür."""
        now = datetime.now(tz=UTC)
        next_day = now.date() + timedelta(days=1)
        next_gen = datetime(
            next_day.year, next_day.month, next_day.day, 8, 0, 0, tzinfo=UTC
        )
        return next_gen.isoformat()


_pulse_service = PulseService()


def get_pulse_service() -> PulseService:
    """PulseService singleton'ını döndürür."""
    return _pulse_service
