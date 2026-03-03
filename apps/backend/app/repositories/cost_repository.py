"""Cost log database repository."""

import uuid
from datetime import date, datetime

from sqlalchemy import Date, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cost_log import CostLog


class CostRepository:
    """Repository for CostLog model database operations."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        model: str,
        input_tokens: int,
        output_tokens: int,
        total_tokens: int,
        cost_usd: float,
        session_id: str | None = None,
        tool_name: str | None = None,
        called_at: datetime | None = None,
    ) -> CostLog:
        """Insert a new cost log entry.

        Args:
            user_id: User who triggered the API call.
            model: AI model identifier.
            input_tokens: Input token count.
            output_tokens: Output token count.
            total_tokens: Total token count.
            cost_usd: Cost in USD.
            session_id: Optional session identifier.
            tool_name: Optional tool name.
            called_at: Timestamp of the call (defaults to now).

        Returns:
            The created CostLog row.
        """
        entry = CostLog(
            user_id=user_id,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            cost_usd=cost_usd,
            session_id=session_id,
            tool_name=tool_name,
        )
        if called_at is not None:
            entry.called_at = called_at
        self._session.add(entry)
        await self._session.flush()
        return entry

    async def list_by_user(
        self,
        user_id: uuid.UUID,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[CostLog]:
        """List cost logs for a specific user, newest first.

        Args:
            user_id: User identifier.
            limit: Max rows to return.
            offset: Rows to skip.

        Returns:
            List of CostLog rows.
        """
        stmt = (
            select(CostLog)
            .where(CostLog.user_id == user_id)
            .order_by(CostLog.called_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_user(self, user_id: uuid.UUID) -> int:
        """Count cost log entries for a user.

        Args:
            user_id: User identifier.

        Returns:
            Entry count.
        """
        stmt = select(func.count()).select_from(CostLog).where(CostLog.user_id == user_id)
        result = await self._session.execute(stmt)
        count = result.scalar_one()
        return int(count)

    async def get_cost_between_dates(
        self,
        start_date: date,
        end_date: date,
        *,
        user_id: uuid.UUID | None = None,
    ) -> list[CostLog]:
        """Get all cost log entries between two dates (inclusive).

        Args:
            start_date: Start date (inclusive).
            end_date: End date (inclusive).
            user_id: Optional user filter.

        Returns:
            List of CostLog rows.
        """
        stmt = select(CostLog).where(
            cast(CostLog.called_at, Date) >= start_date,
            cast(CostLog.called_at, Date) <= end_date,
        )
        if user_id is not None:
            stmt = stmt.where(CostLog.user_id == user_id)
        stmt = stmt.order_by(CostLog.called_at.asc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_daily_totals(
        self,
        start_date: date,
        end_date: date,
        *,
        user_id: uuid.UUID | None = None,
    ) -> list[tuple[date, float, int, int]]:
        """Get daily aggregate totals (date, cost, tokens, call_count).

        Args:
            start_date: Start date (inclusive).
            end_date: End date (inclusive).
            user_id: Optional user filter.

        Returns:
            List of (date, total_cost_usd, total_tokens, call_count) tuples.
        """
        day_col = cast(CostLog.called_at, Date).label("day")
        stmt = (
            select(
                day_col,
                func.sum(CostLog.cost_usd).label("total_cost"),
                func.sum(CostLog.total_tokens).label("total_tokens"),
                func.count().label("call_count"),
            )
            .where(
                cast(CostLog.called_at, Date) >= start_date,
                cast(CostLog.called_at, Date) <= end_date,
            )
            .group_by(day_col)
            .order_by(day_col)
        )
        if user_id is not None:
            stmt = stmt.where(CostLog.user_id == user_id)
        result = await self._session.execute(stmt)
        rows: list[tuple[date, float, int, int]] = []
        for row in result.all():
            rows.append(
                (
                    row.day,
                    float(row.total_cost),
                    int(row.total_tokens),
                    int(row.call_count),
                )
            )
        return rows

    async def get_model_breakdown(
        self,
        start_date: date,
        end_date: date,
        *,
        user_id: uuid.UUID | None = None,
    ) -> list[tuple[str, int, int, int, float, int]]:
        """Get cost breakdown by model.

        Args:
            start_date: Start date (inclusive).
            end_date: End date (inclusive).
            user_id: Optional user filter.

        Returns:
            List of (model, input_tokens, output_tokens, total_tokens, cost, call_count).
        """
        stmt = (
            select(
                CostLog.model,
                func.sum(CostLog.input_tokens).label("total_input"),
                func.sum(CostLog.output_tokens).label("total_output"),
                func.sum(CostLog.total_tokens).label("total_tokens"),
                func.sum(CostLog.cost_usd).label("total_cost"),
                func.count().label("call_count"),
            )
            .where(
                cast(CostLog.called_at, Date) >= start_date,
                cast(CostLog.called_at, Date) <= end_date,
            )
            .group_by(CostLog.model)
            .order_by(func.sum(CostLog.cost_usd).desc())
        )
        if user_id is not None:
            stmt = stmt.where(CostLog.user_id == user_id)
        result = await self._session.execute(stmt)
        rows: list[tuple[str, int, int, int, float, int]] = []
        for row in result.all():
            rows.append(
                (
                    str(row.model),
                    int(row.total_input),
                    int(row.total_output),
                    int(row.total_tokens),
                    float(row.total_cost),
                    int(row.call_count),
                )
            )
        return rows

    async def get_user_totals(
        self,
        start_date: date,
        end_date: date,
    ) -> list[tuple[uuid.UUID, float, int, int]]:
        """Get per-user cost totals.

        Args:
            start_date: Start date (inclusive).
            end_date: End date (inclusive).

        Returns:
            List of (user_id, total_cost, total_tokens, call_count).
        """
        stmt = (
            select(
                CostLog.user_id,
                func.sum(CostLog.cost_usd).label("total_cost"),
                func.sum(CostLog.total_tokens).label("total_tokens"),
                func.count().label("call_count"),
            )
            .where(
                cast(CostLog.called_at, Date) >= start_date,
                cast(CostLog.called_at, Date) <= end_date,
            )
            .group_by(CostLog.user_id)
            .order_by(func.sum(CostLog.cost_usd).desc())
        )
        result = await self._session.execute(stmt)
        rows: list[tuple[uuid.UUID, float, int, int]] = []
        for row in result.all():
            rows.append(
                (
                    row.user_id,
                    float(row.total_cost),
                    int(row.total_tokens),
                    int(row.call_count),
                )
            )
        return rows

    async def get_total_cost_for_date(
        self,
        target_date: date,
        *,
        user_id: uuid.UUID | None = None,
    ) -> float:
        """Get total cost for a specific date.

        Args:
            target_date: The date to query.
            user_id: Optional user filter.

        Returns:
            Total cost in USD.
        """
        stmt = select(func.coalesce(func.sum(CostLog.cost_usd), 0.0)).where(
            cast(CostLog.called_at, Date) == target_date,
        )
        if user_id is not None:
            stmt = stmt.where(CostLog.user_id == user_id)
        result = await self._session.execute(stmt)
        return float(result.scalar_one())

    async def get_total_cost_for_month(
        self,
        year: int,
        month: int,
        *,
        user_id: uuid.UUID | None = None,
    ) -> float:
        """Get total cost for a specific month.

        Args:
            year: Year.
            month: Month (1-12).
            user_id: Optional user filter.

        Returns:
            Total cost in USD.
        """
        stmt = select(func.coalesce(func.sum(CostLog.cost_usd), 0.0)).where(
            func.extract("year", CostLog.called_at) == year,
            func.extract("month", CostLog.called_at) == month,
        )
        if user_id is not None:
            stmt = stmt.where(CostLog.user_id == user_id)
        result = await self._session.execute(stmt)
        return float(result.scalar_one())
