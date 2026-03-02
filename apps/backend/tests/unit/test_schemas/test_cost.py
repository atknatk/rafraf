"""Unit tests for cost Pydantic schemas."""

import uuid
from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from app.schemas.cost import (
    BudgetStatusResponse,
    CostLogCreateRequest,
    CostLogEntity,
    CostLogListResponse,
    CostLogResponse,
    CostReportResponse,
    DailyCostSummary,
    ModelCostBreakdown,
    UserCostSummaryResponse,
)


class TestCostLogEntity:
    """Tests for CostLogEntity frozen model."""

    def test_create_valid(self) -> None:
        """Should create a valid entity with all fields."""
        now = datetime.now(tz=UTC)
        entity = CostLogEntity(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            model="claude-sonnet-4-5-20250929",
            input_tokens=1000,
            output_tokens=500,
            total_tokens=1500,
            cost_usd=0.0105,
            session_id="sess_123",
            tool_name="github_manager",
            called_at=now,
            created_at=now,
        )
        assert entity.model == "claude-sonnet-4-5-20250929"
        assert entity.total_tokens == 1500

    def test_frozen_cannot_modify(self) -> None:
        """Entity should be immutable (frozen)."""
        now = datetime.now(tz=UTC)
        entity = CostLogEntity(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            model="claude-sonnet-4-5-20250929",
            input_tokens=1000,
            output_tokens=500,
            total_tokens=1500,
            cost_usd=0.01,
            session_id=None,
            tool_name=None,
            called_at=now,
            created_at=now,
        )
        with pytest.raises(ValidationError):
            entity.model = "claude-haiku-4-5-20251001"  # type: ignore[misc]

    def test_optional_fields_none(self) -> None:
        """Session ID and tool name should accept None."""
        now = datetime.now(tz=UTC)
        entity = CostLogEntity(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            model="claude-haiku-4-5-20251001",
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
            cost_usd=0.0003,
            session_id=None,
            tool_name=None,
            called_at=now,
            created_at=now,
        )
        assert entity.session_id is None
        assert entity.tool_name is None


class TestCostLogCreateRequest:
    """Tests for CostLogCreateRequest validation."""

    def test_valid_request(self) -> None:
        """Should accept valid request with required fields."""
        req = CostLogCreateRequest(
            user_id=uuid.uuid4(),
            model="claude-sonnet-4-5-20250929",
            input_tokens=1000,
            output_tokens=500,
        )
        assert req.input_tokens == 1000
        assert req.session_id is None
        assert req.tool_name is None

    def test_with_optional_fields(self) -> None:
        """Should accept optional session_id and tool_name."""
        req = CostLogCreateRequest(
            user_id=uuid.uuid4(),
            model="claude-opus-4-5-20250929",
            input_tokens=2000,
            output_tokens=1000,
            session_id="sess_abc",
            tool_name="memory_manager",
        )
        assert req.session_id == "sess_abc"
        assert req.tool_name == "memory_manager"

    def test_negative_input_tokens_rejected(self) -> None:
        """Should reject negative input tokens."""
        with pytest.raises(ValidationError):
            CostLogCreateRequest(
                user_id=uuid.uuid4(),
                model="claude-sonnet-4-5-20250929",
                input_tokens=-1,
                output_tokens=0,
            )

    def test_negative_output_tokens_rejected(self) -> None:
        """Should reject negative output tokens."""
        with pytest.raises(ValidationError):
            CostLogCreateRequest(
                user_id=uuid.uuid4(),
                model="claude-sonnet-4-5-20250929",
                input_tokens=0,
                output_tokens=-1,
            )

    def test_zero_tokens_accepted(self) -> None:
        """Should accept zero token counts."""
        req = CostLogCreateRequest(
            user_id=uuid.uuid4(),
            model="claude-haiku-4-5-20251001",
            input_tokens=0,
            output_tokens=0,
        )
        assert req.input_tokens == 0
        assert req.output_tokens == 0

    def test_model_max_length(self) -> None:
        """Should reject model name exceeding 100 chars."""
        with pytest.raises(ValidationError):
            CostLogCreateRequest(
                user_id=uuid.uuid4(),
                model="x" * 101,
                input_tokens=100,
                output_tokens=50,
            )


class TestModelCostBreakdown:
    """Tests for ModelCostBreakdown frozen model."""

    def test_create_valid(self) -> None:
        """Should create a valid breakdown."""
        breakdown = ModelCostBreakdown(
            model="claude-sonnet-4-5-20250929",
            total_input_tokens=100000,
            total_output_tokens=50000,
            total_tokens=150000,
            total_cost_usd=0.75,
            call_count=10,
        )
        assert breakdown.call_count == 10

    def test_frozen_cannot_modify(self) -> None:
        """Breakdown should be immutable."""
        breakdown = ModelCostBreakdown(
            model="claude-sonnet-4-5-20250929",
            total_input_tokens=100000,
            total_output_tokens=50000,
            total_tokens=150000,
            total_cost_usd=0.75,
            call_count=10,
        )
        with pytest.raises(ValidationError):
            breakdown.model = "changed"  # type: ignore[misc]


class TestDailyCostSummary:
    """Tests for DailyCostSummary frozen model."""

    def test_create_valid(self) -> None:
        """Should create a valid daily summary."""
        summary = DailyCostSummary(
            date=date(2026, 3, 1),
            total_cost_usd=1.25,
            total_tokens=500000,
            call_count=50,
        )
        assert summary.date == date(2026, 3, 1)
        assert summary.total_cost_usd == 1.25

    def test_frozen_cannot_modify(self) -> None:
        """Summary should be immutable."""
        summary = DailyCostSummary(
            date=date(2026, 3, 1),
            total_cost_usd=1.25,
            total_tokens=500000,
            call_count=50,
        )
        with pytest.raises(ValidationError):
            summary.call_count = 99  # type: ignore[misc]


class TestCostReportResponse:
    """Tests for CostReportResponse."""

    def test_create_daily_report(self) -> None:
        """Should create a valid daily report."""
        report = CostReportResponse(
            period="daily",
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 1),
            total_cost_usd=1.50,
            total_input_tokens=200000,
            total_output_tokens=100000,
            total_tokens=300000,
            total_calls=30,
            by_model=[],
            by_day=[],
        )
        assert report.period == "daily"
        assert report.total_calls == 30

    def test_create_monthly_report_with_breakdown(self) -> None:
        """Should create a monthly report with model breakdown."""
        report = CostReportResponse(
            period="monthly",
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 31),
            total_cost_usd=45.0,
            total_input_tokens=5000000,
            total_output_tokens=2000000,
            total_tokens=7000000,
            total_calls=500,
            by_model=[
                ModelCostBreakdown(
                    model="claude-opus-4-5-20250929",
                    total_input_tokens=1000000,
                    total_output_tokens=500000,
                    total_tokens=1500000,
                    total_cost_usd=37.5,
                    call_count=100,
                ),
            ],
            by_day=[
                DailyCostSummary(
                    date=date(2026, 3, 1),
                    total_cost_usd=1.5,
                    total_tokens=300000,
                    call_count=30,
                ),
            ],
        )
        assert len(report.by_model) == 1
        assert len(report.by_day) == 1


class TestCostLogResponse:
    """Tests for CostLogResponse."""

    def test_create_response(self) -> None:
        """Should create a valid response."""
        now = datetime.now(tz=UTC)
        resp = CostLogResponse(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            model="claude-sonnet-4-5-20250929",
            input_tokens=1000,
            output_tokens=500,
            total_tokens=1500,
            cost_usd=0.0105,
            session_id=None,
            tool_name=None,
            called_at=now,
            created_at=now,
        )
        assert resp.cost_usd == 0.0105


class TestCostLogListResponse:
    """Tests for CostLogListResponse."""

    def test_empty_list(self) -> None:
        """Should accept empty items list."""
        resp = CostLogListResponse(items=[], total=0)
        assert resp.total == 0

    def test_with_items(self) -> None:
        """Should accept list with items."""
        now = datetime.now(tz=UTC)
        item = CostLogResponse(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            model="claude-haiku-4-5-20251001",
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
            cost_usd=0.0003,
            session_id=None,
            tool_name=None,
            called_at=now,
            created_at=now,
        )
        resp = CostLogListResponse(items=[item], total=1)
        assert resp.total == 1
        assert len(resp.items) == 1


class TestUserCostSummaryResponse:
    """Tests for UserCostSummaryResponse."""

    def test_create_summary(self) -> None:
        """Should create a valid user summary."""
        summary = UserCostSummaryResponse(
            user_id=uuid.uuid4(),
            total_cost_usd=5.50,
            total_tokens=1000000,
            call_count=100,
        )
        assert summary.total_cost_usd == 5.50
        assert summary.call_count == 100


class TestBudgetStatusResponse:
    """Tests for BudgetStatusResponse."""

    def test_within_budget(self) -> None:
        """Should report within budget when limits not exceeded."""
        status = BudgetStatusResponse(
            daily_cost_usd=5.0,
            monthly_cost_usd=50.0,
            daily_limit_usd=10.0,
            monthly_limit_usd=100.0,
            daily_limit_exceeded=False,
            monthly_limit_exceeded=False,
        )
        assert not status.daily_limit_exceeded
        assert not status.monthly_limit_exceeded

    def test_exceeded_budget(self) -> None:
        """Should report exceeded when over limits."""
        status = BudgetStatusResponse(
            daily_cost_usd=15.0,
            monthly_cost_usd=120.0,
            daily_limit_usd=10.0,
            monthly_limit_usd=100.0,
            daily_limit_exceeded=True,
            monthly_limit_exceeded=True,
        )
        assert status.daily_limit_exceeded
        assert status.monthly_limit_exceeded

    def test_no_limits_set(self) -> None:
        """Should accept None limits."""
        status = BudgetStatusResponse(
            daily_cost_usd=5.0,
            monthly_cost_usd=50.0,
            daily_limit_usd=None,
            monthly_limit_usd=None,
            daily_limit_exceeded=False,
            monthly_limit_exceeded=False,
        )
        assert status.daily_limit_usd is None
        assert status.monthly_limit_usd is None
