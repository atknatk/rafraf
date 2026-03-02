"""Unit tests for CostService."""

import uuid
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.cost_service import CostService, CostServiceError


class TestCalculateCost:
    """Tests for CostService.calculate_cost static method."""

    def test_opus_model_pricing(self) -> None:
        """Should calculate cost for Opus model correctly."""
        cost = CostService.calculate_cost(
            "claude-opus-4-5-20250929",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
        )
        # Input: 1M * $15/1M = $15.00, Output: 1M * $75/1M = $75.00
        assert cost == 90.0

    def test_sonnet_model_pricing(self) -> None:
        """Should calculate cost for Sonnet model correctly."""
        cost = CostService.calculate_cost(
            "claude-sonnet-4-5-20250929",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
        )
        # Input: 1M * $3/1M = $3.00, Output: 1M * $15/1M = $15.00
        assert cost == 18.0

    def test_haiku_model_pricing(self) -> None:
        """Should calculate cost for Haiku model correctly."""
        cost = CostService.calculate_cost(
            "claude-haiku-4-5-20251001",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
        )
        # Input: 1M * $0.80/1M = $0.80, Output: 1M * $4/1M = $4.00
        assert cost == 4.8

    def test_unknown_model_uses_fallback(self) -> None:
        """Should use default pricing for unknown models."""
        cost = CostService.calculate_cost(
            "unknown-model-v1",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
        )
        # Default: Input $3/1M, Output $15/1M
        assert cost == 18.0

    def test_zero_tokens(self) -> None:
        """Should return zero cost for zero tokens."""
        cost = CostService.calculate_cost(
            "claude-sonnet-4-5-20250929",
            input_tokens=0,
            output_tokens=0,
        )
        assert cost == 0.0

    def test_small_token_count(self) -> None:
        """Should calculate fractional costs correctly for small counts."""
        cost = CostService.calculate_cost(
            "claude-sonnet-4-5-20250929",
            input_tokens=1000,
            output_tokens=500,
        )
        # Input: 1000/1M * $3 = $0.003, Output: 500/1M * $15 = $0.0075
        assert cost == pytest.approx(0.0105, abs=1e-6)

    def test_only_input_tokens(self) -> None:
        """Should calculate cost with only input tokens."""
        cost = CostService.calculate_cost(
            "claude-sonnet-4-5-20250929",
            input_tokens=10000,
            output_tokens=0,
        )
        assert cost == pytest.approx(0.03, abs=1e-6)

    def test_only_output_tokens(self) -> None:
        """Should calculate cost with only output tokens."""
        cost = CostService.calculate_cost(
            "claude-sonnet-4-5-20250929",
            input_tokens=0,
            output_tokens=10000,
        )
        assert cost == pytest.approx(0.15, abs=1e-6)


class TestRecordUsage:
    """Tests for CostService.record_usage."""

    async def test_record_success(self) -> None:
        """Should create a cost log entry with calculated cost."""
        service = CostService()
        user_id = uuid.uuid4()
        now = datetime.now(tz=UTC)

        mock_row = MagicMock()
        mock_row.id = uuid.uuid4()
        mock_row.user_id = user_id
        mock_row.model = "claude-sonnet-4-5-20250929"
        mock_row.input_tokens = 1000
        mock_row.output_tokens = 500
        mock_row.total_tokens = 1500
        mock_row.cost_usd = 0.0105
        mock_row.session_id = None
        mock_row.tool_name = None
        mock_row.called_at = now
        mock_row.created_at = now

        mock_repo = AsyncMock()
        mock_repo.create = AsyncMock(return_value=mock_row)

        entity = await service.record_usage(
            mock_repo,
            user_id=user_id,
            model="claude-sonnet-4-5-20250929",
            input_tokens=1000,
            output_tokens=500,
        )

        mock_repo.create.assert_called_once()
        call_kwargs = mock_repo.create.call_args.kwargs
        assert call_kwargs["user_id"] == user_id
        assert call_kwargs["total_tokens"] == 1500
        assert entity.model == "claude-sonnet-4-5-20250929"

    async def test_record_with_session_and_tool(self) -> None:
        """Should pass session_id and tool_name to repository."""
        service = CostService()
        user_id = uuid.uuid4()
        now = datetime.now(tz=UTC)

        mock_row = MagicMock()
        mock_row.id = uuid.uuid4()
        mock_row.user_id = user_id
        mock_row.model = "claude-haiku-4-5-20251001"
        mock_row.input_tokens = 100
        mock_row.output_tokens = 50
        mock_row.total_tokens = 150
        mock_row.cost_usd = 0.0003
        mock_row.session_id = "sess_abc"
        mock_row.tool_name = "github_manager"
        mock_row.called_at = now
        mock_row.created_at = now

        mock_repo = AsyncMock()
        mock_repo.create = AsyncMock(return_value=mock_row)

        entity = await service.record_usage(
            mock_repo,
            user_id=user_id,
            model="claude-haiku-4-5-20251001",
            input_tokens=100,
            output_tokens=50,
            session_id="sess_abc",
            tool_name="github_manager",
        )

        call_kwargs = mock_repo.create.call_args.kwargs
        assert call_kwargs["session_id"] == "sess_abc"
        assert call_kwargs["tool_name"] == "github_manager"
        assert entity.session_id == "sess_abc"


class TestGetUserLogs:
    """Tests for CostService.get_user_logs."""

    async def test_returns_paginated_results(self) -> None:
        """Should return items and total count."""
        service = CostService()
        user_id = uuid.uuid4()
        now = datetime.now(tz=UTC)

        mock_row = MagicMock()
        mock_row.id = uuid.uuid4()
        mock_row.user_id = user_id
        mock_row.model = "claude-sonnet-4-5-20250929"
        mock_row.input_tokens = 1000
        mock_row.output_tokens = 500
        mock_row.total_tokens = 1500
        mock_row.cost_usd = 0.0105
        mock_row.session_id = None
        mock_row.tool_name = None
        mock_row.called_at = now
        mock_row.created_at = now

        mock_repo = AsyncMock()
        mock_repo.list_by_user = AsyncMock(return_value=[mock_row])
        mock_repo.count_by_user = AsyncMock(return_value=1)

        items, total = await service.get_user_logs(mock_repo, user_id)

        assert len(items) == 1
        assert total == 1
        mock_repo.list_by_user.assert_called_once_with(
            user_id, limit=50, offset=0
        )

    async def test_empty_results(self) -> None:
        """Should return empty list and zero total."""
        service = CostService()
        user_id = uuid.uuid4()

        mock_repo = AsyncMock()
        mock_repo.list_by_user = AsyncMock(return_value=[])
        mock_repo.count_by_user = AsyncMock(return_value=0)

        items, total = await service.get_user_logs(mock_repo, user_id)

        assert items == []
        assert total == 0


class TestGenerateReport:
    """Tests for CostService.generate_report."""

    async def test_daily_report(self) -> None:
        """Should generate a daily report."""
        service = CostService()
        target = date(2026, 3, 1)

        mock_repo = AsyncMock()
        mock_repo.get_model_breakdown = AsyncMock(return_value=[
            ("claude-sonnet-4-5-20250929", 10000, 5000, 15000, 0.105, 10),
        ])
        mock_repo.get_daily_totals = AsyncMock(return_value=[
            (date(2026, 3, 1), 0.105, 15000, 10),
        ])

        report = await service.generate_report(
            mock_repo, period="daily", target_date=target
        )

        assert report.period == "daily"
        assert report.start_date == target
        assert report.end_date == target
        assert report.total_calls == 10
        assert len(report.by_model) == 1
        assert len(report.by_day) == 1

    async def test_monthly_report(self) -> None:
        """Should generate a monthly report with correct date range."""
        service = CostService()
        target = date(2026, 3, 15)

        mock_repo = AsyncMock()
        mock_repo.get_model_breakdown = AsyncMock(return_value=[])
        mock_repo.get_daily_totals = AsyncMock(return_value=[])

        report = await service.generate_report(
            mock_repo, period="monthly", target_date=target
        )

        assert report.period == "monthly"
        assert report.start_date == date(2026, 3, 1)
        assert report.end_date == date(2026, 3, 31)

    async def test_monthly_report_december(self) -> None:
        """Should handle December correctly (year rollover)."""
        service = CostService()
        target = date(2026, 12, 10)

        mock_repo = AsyncMock()
        mock_repo.get_model_breakdown = AsyncMock(return_value=[])
        mock_repo.get_daily_totals = AsyncMock(return_value=[])

        report = await service.generate_report(
            mock_repo, period="monthly", target_date=target
        )

        assert report.start_date == date(2026, 12, 1)
        assert report.end_date == date(2026, 12, 31)

    async def test_invalid_period_raises_error(self) -> None:
        """Should raise CostServiceError for invalid period."""
        service = CostService()
        mock_repo = AsyncMock()

        with pytest.raises(CostServiceError, match="Gecersiz period"):
            await service.generate_report(
                mock_repo, period="weekly"
            )

    async def test_report_totals_multiple_models(self) -> None:
        """Should sum totals across multiple models."""
        service = CostService()

        mock_repo = AsyncMock()
        mock_repo.get_model_breakdown = AsyncMock(return_value=[
            ("claude-opus-4-5-20250929", 5000, 2000, 7000, 1.0, 5),
            ("claude-sonnet-4-5-20250929", 3000, 1000, 4000, 0.5, 3),
        ])
        mock_repo.get_daily_totals = AsyncMock(return_value=[])

        report = await service.generate_report(
            mock_repo, period="daily", target_date=date(2026, 3, 1)
        )

        assert report.total_cost_usd == pytest.approx(1.5, abs=1e-4)
        assert report.total_input_tokens == 8000
        assert report.total_output_tokens == 3000
        assert report.total_tokens == 11000
        assert report.total_calls == 8


class TestGetBudgetStatus:
    """Tests for CostService.get_budget_status."""

    async def test_within_budget(self) -> None:
        """Should report not exceeded when costs below limits."""
        service = CostService()

        mock_repo = AsyncMock()
        mock_repo.get_total_cost_for_date = AsyncMock(return_value=5.0)
        mock_repo.get_total_cost_for_month = AsyncMock(return_value=50.0)

        status = await service.get_budget_status(
            mock_repo,
            daily_limit_usd=10.0,
            monthly_limit_usd=100.0,
        )

        assert not status.daily_limit_exceeded
        assert not status.monthly_limit_exceeded
        assert status.daily_cost_usd == pytest.approx(5.0, abs=1e-4)
        assert status.monthly_cost_usd == pytest.approx(50.0, abs=1e-4)

    async def test_daily_limit_exceeded(self) -> None:
        """Should flag daily limit exceeded."""
        service = CostService()

        mock_repo = AsyncMock()
        mock_repo.get_total_cost_for_date = AsyncMock(return_value=15.0)
        mock_repo.get_total_cost_for_month = AsyncMock(return_value=50.0)

        status = await service.get_budget_status(
            mock_repo,
            daily_limit_usd=10.0,
            monthly_limit_usd=100.0,
        )

        assert status.daily_limit_exceeded
        assert not status.monthly_limit_exceeded

    async def test_monthly_limit_exceeded(self) -> None:
        """Should flag monthly limit exceeded."""
        service = CostService()

        mock_repo = AsyncMock()
        mock_repo.get_total_cost_for_date = AsyncMock(return_value=5.0)
        mock_repo.get_total_cost_for_month = AsyncMock(return_value=120.0)

        status = await service.get_budget_status(
            mock_repo,
            daily_limit_usd=10.0,
            monthly_limit_usd=100.0,
        )

        assert not status.daily_limit_exceeded
        assert status.monthly_limit_exceeded

    async def test_no_limits_set(self) -> None:
        """Should not flag exceeded when no limits set."""
        service = CostService()

        mock_repo = AsyncMock()
        mock_repo.get_total_cost_for_date = AsyncMock(return_value=999.0)
        mock_repo.get_total_cost_for_month = AsyncMock(return_value=9999.0)

        status = await service.get_budget_status(mock_repo)

        assert not status.daily_limit_exceeded
        assert not status.monthly_limit_exceeded
        assert status.daily_limit_usd is None
        assert status.monthly_limit_usd is None

    async def test_exact_limit_triggers_exceeded(self) -> None:
        """Should flag exceeded at exactly the limit."""
        service = CostService()

        mock_repo = AsyncMock()
        mock_repo.get_total_cost_for_date = AsyncMock(return_value=10.0)
        mock_repo.get_total_cost_for_month = AsyncMock(return_value=100.0)

        status = await service.get_budget_status(
            mock_repo,
            daily_limit_usd=10.0,
            monthly_limit_usd=100.0,
        )

        assert status.daily_limit_exceeded
        assert status.monthly_limit_exceeded


class TestGetUserSummaries:
    """Tests for CostService.get_user_summaries."""

    async def test_returns_summaries(self) -> None:
        """Should return per-user summaries."""
        service = CostService()
        uid1 = uuid.uuid4()
        uid2 = uuid.uuid4()

        mock_repo = AsyncMock()
        mock_repo.get_user_totals = AsyncMock(return_value=[
            (uid1, 10.0, 500000, 50),
            (uid2, 5.0, 200000, 20),
        ])

        summaries = await service.get_user_summaries(
            mock_repo,
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 31),
        )

        assert len(summaries) == 2
        assert summaries[0].user_id == uid1
        assert summaries[0].total_cost_usd == 10.0
        assert summaries[1].user_id == uid2

    async def test_empty_summaries(self) -> None:
        """Should return empty list when no users."""
        service = CostService()

        mock_repo = AsyncMock()
        mock_repo.get_user_totals = AsyncMock(return_value=[])

        summaries = await service.get_user_summaries(mock_repo)

        assert summaries == []


class TestGetSupportedModels:
    """Tests for CostService.get_supported_models."""

    def test_returns_model_list(self) -> None:
        """Should return non-empty list of models."""
        models = CostService.get_supported_models()
        assert len(models) >= 3  # At least Opus, Sonnet, Haiku

    def test_model_has_required_fields(self) -> None:
        """Each model should have model name and pricing fields."""
        models = CostService.get_supported_models()
        for model_info in models:
            assert "model" in model_info
            assert "input_price_per_1m" in model_info
            assert "output_price_per_1m" in model_info

    def test_opus_pricing_present(self) -> None:
        """Opus model should be in the supported list."""
        models = CostService.get_supported_models()
        opus_models = [m for m in models if "opus" in str(m["model"])]
        assert len(opus_models) == 1
        assert opus_models[0]["input_price_per_1m"] == 15.0
        assert opus_models[0]["output_price_per_1m"] == 75.0
