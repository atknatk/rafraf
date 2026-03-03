"""Cost tracker service - token usage recording, model-based cost calculation, reporting."""

import uuid
from datetime import UTC, date, datetime, timedelta

import structlog

from app.models.cost_log import CostLog
from app.repositories.cost_repository import CostRepository
from app.schemas.cost import (
    BudgetStatusResponse,
    CostLogEntity,
    CostLogResponse,
    CostReportResponse,
    DailyCostSummary,
    ModelCostBreakdown,
    UserCostSummaryResponse,
)

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

# Model pricing per 1M tokens (USD).
# Values based on Anthropic published pricing as of 2025.
_MODEL_PRICING: dict[str, dict[str, float]] = {
    # Direct Anthropic API
    "claude-opus-4-5-20250929": {"input": 15.0, "output": 75.0},
    "claude-sonnet-4-5-20250929": {"input": 3.0, "output": 15.0},
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.0},
    # AWS Bedrock EU inference profiles
    "eu.anthropic.claude-opus-4-5-20251101-v1:0": {"input": 15.0, "output": 75.0},
    "eu.anthropic.claude-sonnet-4-5-20250929-v1:0": {"input": 3.0, "output": 15.0},
    "eu.anthropic.claude-haiku-4-5-20251001-v1:0": {"input": 0.80, "output": 4.0},
}

# Fallback pricing for unknown models
_DEFAULT_PRICING: dict[str, float] = {"input": 3.0, "output": 15.0}

# Default budget limits (can be overridden per-user via Redis in a future iteration)
_DEFAULT_DAILY_LIMIT_USD: float | None = None
_DEFAULT_MONTHLY_LIMIT_USD: float | None = None


class CostServiceError(Exception):
    """Raised when a cost service operation fails."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class CostService:
    """Service for AI API cost tracking and reporting.

    Responsibilities:
    - Calculate cost from token usage and model pricing
    - Record cost log entries
    - Generate daily/monthly reports
    - Check budget limits
    - Provide per-user cost summaries
    """

    @staticmethod
    def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
        """Calculate the USD cost for an API call based on model pricing.

        Args:
            model: AI model identifier.
            input_tokens: Number of input tokens.
            output_tokens: Number of output tokens.

        Returns:
            Cost in USD.
        """
        pricing = _MODEL_PRICING.get(model, _DEFAULT_PRICING)
        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]
        return round(input_cost + output_cost, 8)

    async def record_usage(
        self,
        repo: CostRepository,
        *,
        user_id: uuid.UUID,
        model: str,
        input_tokens: int,
        output_tokens: int,
        session_id: str | None = None,
        tool_name: str | None = None,
    ) -> CostLogEntity:
        """Record a new API call cost entry.

        Args:
            repo: Cost repository instance.
            user_id: User who triggered the API call.
            model: AI model used.
            input_tokens: Input token count.
            output_tokens: Output token count.
            session_id: Optional session identifier.
            tool_name: Optional tool name.

        Returns:
            The created cost log entity.
        """
        total_tokens = input_tokens + output_tokens
        cost_usd = self.calculate_cost(model, input_tokens, output_tokens)

        row = await repo.create(
            user_id=user_id,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            cost_usd=cost_usd,
            session_id=session_id,
            tool_name=tool_name,
        )

        await logger.ainfo(
            "cost_recorded",
            user_id=str(user_id),
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
        )

        return self._to_entity(row)

    async def get_user_logs(
        self,
        repo: CostRepository,
        user_id: uuid.UUID,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[CostLogResponse], int]:
        """Get paginated cost logs for a user.

        Args:
            repo: Cost repository instance.
            user_id: User identifier.
            limit: Max entries per page.
            offset: Entries to skip.

        Returns:
            Tuple of (items, total_count).
        """
        rows = await repo.list_by_user(user_id, limit=limit, offset=offset)
        total = await repo.count_by_user(user_id)
        items = [self._to_response(row) for row in rows]
        return items, total

    async def generate_report(
        self,
        repo: CostRepository,
        *,
        period: str,
        target_date: date | None = None,
        user_id: uuid.UUID | None = None,
    ) -> CostReportResponse:
        """Generate a cost report for a daily or monthly period.

        Args:
            repo: Cost repository instance.
            period: 'daily' or 'monthly'.
            target_date: Date to report on (defaults to today).
            user_id: Optional user filter.

        Returns:
            CostReportResponse with aggregated data.

        Raises:
            CostServiceError: If period is invalid.
        """
        if period not in ("daily", "monthly"):
            raise CostServiceError(f"Gecersiz period: {period}. 'daily' veya 'monthly' olmali.")

        if target_date is None:
            target_date = datetime.now(tz=UTC).date()

        if period == "daily":
            start = target_date
            end = target_date
        else:
            start = target_date.replace(day=1)
            # Last day of the month
            if target_date.month == 12:
                end = target_date.replace(year=target_date.year + 1, month=1, day=1) - timedelta(
                    days=1
                )
            else:
                end = target_date.replace(month=target_date.month + 1, day=1) - timedelta(days=1)

        # Fetch aggregate data
        model_rows = await repo.get_model_breakdown(start, end, user_id=user_id)
        daily_rows = await repo.get_daily_totals(start, end, user_id=user_id)

        # Compute totals
        total_cost = sum(r[4] for r in model_rows)
        total_input = sum(r[1] for r in model_rows)
        total_output = sum(r[2] for r in model_rows)
        total_tokens = sum(r[3] for r in model_rows)
        total_calls = sum(r[5] for r in model_rows)

        by_model = [
            ModelCostBreakdown(
                model=r[0],
                total_input_tokens=r[1],
                total_output_tokens=r[2],
                total_tokens=r[3],
                total_cost_usd=r[4],
                call_count=r[5],
            )
            for r in model_rows
        ]

        by_day = [
            DailyCostSummary(
                date=r[0],
                total_cost_usd=r[1],
                total_tokens=r[2],
                call_count=r[3],
            )
            for r in daily_rows
        ]

        return CostReportResponse(
            period=period,
            start_date=start,
            end_date=end,
            total_cost_usd=round(total_cost, 6),
            total_input_tokens=total_input,
            total_output_tokens=total_output,
            total_tokens=total_tokens,
            total_calls=total_calls,
            by_model=by_model,
            by_day=by_day,
        )

    async def get_user_summaries(
        self,
        repo: CostRepository,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[UserCostSummaryResponse]:
        """Get per-user cost summaries for a date range.

        Args:
            repo: Cost repository instance.
            start_date: Start date (defaults to first of month).
            end_date: End date (defaults to today).

        Returns:
            List of per-user summaries.
        """
        today = datetime.now(tz=UTC).date()
        if start_date is None:
            start_date = today.replace(day=1)
        if end_date is None:
            end_date = today

        rows = await repo.get_user_totals(start_date, end_date)
        return [
            UserCostSummaryResponse(
                user_id=r[0],
                total_cost_usd=round(r[1], 6),
                total_tokens=r[2],
                call_count=r[3],
            )
            for r in rows
        ]

    async def get_budget_status(
        self,
        repo: CostRepository,
        *,
        user_id: uuid.UUID | None = None,
        daily_limit_usd: float | None = None,
        monthly_limit_usd: float | None = None,
    ) -> BudgetStatusResponse:
        """Check current budget status and alert flags.

        Args:
            repo: Cost repository instance.
            user_id: Optional user filter.
            daily_limit_usd: Daily budget limit (overrides default).
            monthly_limit_usd: Monthly budget limit (overrides default).

        Returns:
            BudgetStatusResponse with current costs and alert flags.
        """
        today = datetime.now(tz=UTC).date()
        daily_cost = await repo.get_total_cost_for_date(today, user_id=user_id)
        monthly_cost = await repo.get_total_cost_for_month(today.year, today.month, user_id=user_id)

        daily_limit = daily_limit_usd if daily_limit_usd is not None else _DEFAULT_DAILY_LIMIT_USD
        monthly_limit = (
            monthly_limit_usd if monthly_limit_usd is not None else _DEFAULT_MONTHLY_LIMIT_USD
        )

        daily_exceeded = daily_limit is not None and daily_cost >= daily_limit
        monthly_exceeded = monthly_limit is not None and monthly_cost >= monthly_limit

        if daily_exceeded:
            await logger.awarning(
                "budget_daily_limit_exceeded",
                daily_cost=daily_cost,
                daily_limit=daily_limit,
                user_id=str(user_id) if user_id else None,
            )

        if monthly_exceeded:
            await logger.awarning(
                "budget_monthly_limit_exceeded",
                monthly_cost=monthly_cost,
                monthly_limit=monthly_limit,
                user_id=str(user_id) if user_id else None,
            )

        return BudgetStatusResponse(
            daily_cost_usd=round(daily_cost, 6),
            monthly_cost_usd=round(monthly_cost, 6),
            daily_limit_usd=daily_limit,
            monthly_limit_usd=monthly_limit,
            daily_limit_exceeded=daily_exceeded,
            monthly_limit_exceeded=monthly_exceeded,
        )

    @staticmethod
    def get_supported_models() -> list[dict[str, object]]:
        """Return the list of supported models with their pricing.

        Returns:
            List of model pricing info dicts.
        """
        models: list[dict[str, object]] = []
        for model_name, pricing in _MODEL_PRICING.items():
            models.append(
                {
                    "model": model_name,
                    "input_price_per_1m": pricing["input"],
                    "output_price_per_1m": pricing["output"],
                }
            )
        return models

    @staticmethod
    def _to_entity(row: CostLog) -> CostLogEntity:
        """Convert a CostLog row to a frozen domain entity.

        Args:
            row: SQLAlchemy CostLog row.

        Returns:
            CostLogEntity instance.
        """
        return CostLogEntity(
            id=row.id,
            user_id=row.user_id,
            model=row.model,
            input_tokens=row.input_tokens,
            output_tokens=row.output_tokens,
            total_tokens=row.total_tokens,
            cost_usd=row.cost_usd,
            session_id=row.session_id,
            tool_name=row.tool_name,
            called_at=row.called_at,
            created_at=row.created_at,
        )

    @staticmethod
    def _to_response(row: CostLog) -> CostLogResponse:
        """Convert a CostLog row to a response schema.

        Args:
            row: SQLAlchemy CostLog row.

        Returns:
            CostLogResponse instance.
        """
        return CostLogResponse(
            id=row.id,
            user_id=row.user_id,
            model=row.model,
            input_tokens=row.input_tokens,
            output_tokens=row.output_tokens,
            total_tokens=row.total_tokens,
            cost_usd=row.cost_usd,
            session_id=row.session_id,
            tool_name=row.tool_name,
            called_at=row.called_at,
            created_at=row.created_at,
        )


# Module-level singleton
cost_service = CostService()
