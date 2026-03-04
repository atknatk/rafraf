"""Subscription usage tracking schemas (Pydantic v2)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class DailyUsageStats(BaseModel):
    """Single day usage statistics."""

    date: str = Field(..., description="Tarih (YYYY-MM-DD)")
    message_count: int = Field(0, ge=0, description="Mesaj sayisi")
    session_count: int = Field(0, ge=0, description="Session sayisi")
    tool_call_count: int = Field(0, ge=0, description="Tool cagri sayisi")


class SubscriptionUsageResponse(BaseModel):
    """Response for subscription usage endpoint."""

    subscription_type: str = Field(..., description="Plan tipi (max, pro, free)")
    email: str | None = Field(None, description="Hesap email")
    org_name: str | None = Field(None, description="Organizasyon adi")
    today_usage: DailyUsageStats = Field(..., description="Bugunun kullanim verileri")
    recent_days: list[DailyUsageStats] = Field(
        default_factory=list, description="Son 7 gun kullanim"
    )
    total_messages_today: int = Field(
        0, ge=0, description="claude -p ile bugun gonderilen mesaj sayisi"
    )
    is_rate_limited: bool = Field(False, description="Son 10 dk icinde rate limit alindi mi")
    rate_limit_reset_at: str | None = Field(None, description="Rate limit reset zamani (ISO 8601)")
    last_fetched_at: str = Field(..., description="Verinin alinma zamani (ISO 8601)")
