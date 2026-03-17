"""Monitoring dashboard schemas (Pydantic v2)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ComponentHealth(BaseModel):
    """Single component health status."""

    model_config = ConfigDict(frozen=True)

    name: str
    status: str = Field(description="up | down")
    latency_ms: float | None = None
    detail: str | None = None


class SystemHealth(BaseModel):
    """Backend system health snapshot."""

    model_config = ConfigDict(frozen=True)

    status: str = Field(description="healthy | degraded | unhealthy")
    uptime_seconds: float = 0
    started_at: str = ""
    cpu_percent: float = 0
    memory_percent: float = 0
    memory_used_mb: float = 0
    components: list[ComponentHealth] = Field(default_factory=list)


class AgentOverview(BaseModel):
    """Agent fleet summary."""

    model_config = ConfigDict(frozen=True)

    total: int = 0
    online: int = 0
    offline: int = 0
    busy: int = 0
    agents: list[AgentBrief] = Field(default_factory=list)


class AgentBrief(BaseModel):
    """Minimal agent info for dashboard."""

    model_config = ConfigDict(frozen=True)

    host_id: str
    status: str
    cpu_percent: float = 0
    memory_percent: float = 0
    active_tasks: int = 0
    uptime_seconds: int = 0


class UsageOverview(BaseModel):
    """Subscription usage summary."""

    model_config = ConfigDict(frozen=True)

    subscription_type: str = "unknown"
    usage_percent: float = 0
    daily_message_limit: int = 0
    total_messages_today: int = 0
    is_rate_limited: bool = False
    warning_threshold_reached: bool = False
    limit_exceeded: bool = False


class PulseSummary(BaseModel):
    """Latest pulse report summary."""

    model_config = ConfigDict(frozen=True)

    summary_text: str = ""
    total_messages: int = 0
    total_cost_usd: float | None = None
    report_date: str = ""
    risks: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class MonitoringDashboardResponse(BaseModel):
    """Aggregated monitoring dashboard response."""

    model_config = ConfigDict(frozen=True)

    timestamp: str
    system: SystemHealth
    agents: AgentOverview
    usage: UsageOverview
    pulse: PulseSummary | None = None


# Forward ref update for AgentOverview.agents
AgentOverview.model_rebuild()
