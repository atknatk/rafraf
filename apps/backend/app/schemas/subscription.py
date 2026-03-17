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
    usage_percent: float = Field(0.0, ge=0, le=100, description="Gunluk kullanim yuzdesi (0-100)")
    daily_message_limit: int = Field(0, ge=0, description="Gunluk mesaj limiti")
    warning_threshold_reached: bool = Field(
        False, description="Kullanim warning esigini (%80) gecti mi"
    )
    limit_exceeded: bool = Field(False, description="Gunluk limit asildi mi")
    last_fetched_at: str = Field(..., description="Verinin alinma zamani (ISO 8601)")
