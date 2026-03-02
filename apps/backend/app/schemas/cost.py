"""Pydantic request/response schemas for the cost tracker."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

# --- Domain entities (frozen) ---


class CostLogEntity(BaseModel):
    """Immutable cost log domain entity."""

    model_config = ConfigDict(frozen=True)

    id: uuid.UUID
    user_id: uuid.UUID
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_usd: float
    session_id: str | None
    tool_name: str | None
    called_at: datetime
    created_at: datetime


# --- Request schemas ---


class CostLogCreateRequest(BaseModel):
    """Request to create a cost log entry."""

    user_id: uuid.UUID
    model: str = Field(max_length=100)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    session_id: str | None = Field(default=None, max_length=255)
    tool_name: str | None = Field(default=None, max_length=100)


class BudgetAlertRequest(BaseModel):
    """Request to set a budget alert threshold."""

    user_id: uuid.UUID | None = None
    daily_limit_usd: float | None = Field(default=None, ge=0.0)
    monthly_limit_usd: float | None = Field(default=None, ge=0.0)


# --- Response schemas ---


class CostLogResponse(BaseModel):
    """Single cost log entry response."""

    id: uuid.UUID
    user_id: uuid.UUID
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_usd: float
    session_id: str | None
    tool_name: str | None
    called_at: datetime
    created_at: datetime


class CostLogListResponse(BaseModel):
    """Paginated list of cost log entries."""

    items: list[CostLogResponse]
    total: int


class ModelCostBreakdown(BaseModel):
    """Cost breakdown for a single model."""

    model_config = ConfigDict(frozen=True)

    model: str
    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int
    total_cost_usd: float
    call_count: int


class DailyCostSummary(BaseModel):
    """Cost summary for a single day."""

    model_config = ConfigDict(frozen=True)

    date: date
    total_cost_usd: float
    total_tokens: int
    call_count: int


class CostReportResponse(BaseModel):
    """Aggregated cost report (daily or monthly)."""

    period: str
    start_date: date
    end_date: date
    total_cost_usd: float
    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int
    total_calls: int
    by_model: list[ModelCostBreakdown]
    by_day: list[DailyCostSummary]


class UserCostSummaryResponse(BaseModel):
    """Per-user cost summary."""

    user_id: uuid.UUID
    total_cost_usd: float
    total_tokens: int
    call_count: int


class BudgetStatusResponse(BaseModel):
    """Current budget status and alerts."""

    daily_cost_usd: float
    monthly_cost_usd: float
    daily_limit_usd: float | None
    monthly_limit_usd: float | None
    daily_limit_exceeded: bool
    monthly_limit_exceeded: bool
