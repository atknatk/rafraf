"""Pydantic schemas for Pulse Report API."""

from pydantic import BaseModel, ConfigDict


class PulseReportResponse(BaseModel):
    """API response for a pulse report."""

    model_config = ConfigDict(frozen=True)

    id: str
    report_date: str  # ISO date string
    period_start: str  # ISO datetime
    period_end: str
    total_messages: int
    user_messages: int
    assistant_messages: int
    total_cost_usd: float | None
    models_used: list[str]
    summary_text: str
    completed_items: list[str]
    in_progress_items: list[str]
    risks: list[str]
    suggestions: list[str]
    generated_at: str  # created_at ISO datetime


class PulseNotAvailableResponse(BaseModel):
    """Response when no pulse is available."""

    model_config = ConfigDict(frozen=True)

    message: str
    next_generation_at: str | None = None
