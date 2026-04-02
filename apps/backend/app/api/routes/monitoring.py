"""Monitoring dashboard endpoint — birlesik sistem durumu."""

from __future__ import annotations

import shutil
import time
from datetime import UTC, datetime

import psutil
import structlog
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.routes.health import _START_DATETIME, _START_TIME
from app.api.routes.websocket import manager
from app.schemas.monitoring import (
    AgentBrief,
    AgentOverview,
    ComponentHealth,
    MonitoringDashboardResponse,
    PulseSummary,
    SystemHealth,
    UsageOverview,
)
from app.services.agent_registry_service import agent_registry

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/monitoring", tags=["monitoring"])


@router.get("/dashboard", response_model=MonitoringDashboardResponse)
async def get_monitoring_dashboard(
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> MonitoringDashboardResponse:
    """Birlesik monitoring dashboard — system health + agents + usage + pulse."""
    now = datetime.now(tz=UTC)

    # --- System Health ---
    system = await _build_system_health(db)

    # --- Agent Overview ---
    agents = _build_agent_overview()

    # --- Usage Overview ---
    usage = await _build_usage_overview()

    # --- Pulse Summary ---
    pulse = await _build_pulse_summary(db)

    return MonitoringDashboardResponse(
        timestamp=now.isoformat(),
        system=system,
        agents=agents,
        usage=usage,
        pulse=pulse,
    )


async def _build_system_health(db: AsyncSession) -> SystemHealth:
    """Collect system component health data."""
    components: list[ComponentHealth] = []
    down_count = 0

    # Database
    db_start = time.monotonic()
    try:
        await db.execute(text("SELECT 1"))
        latency = round((time.monotonic() - db_start) * 1000, 2)
        components.append(ComponentHealth(name="database", status="up", latency_ms=latency))
    except Exception:
        components.append(ComponentHealth(name="database", status="down"))
        down_count += 1

    # Redis
    from app.core.redis import redis_client

    redis_start = time.monotonic()
    try:
        client = await redis_client._get_client()
        await client.ping()  # type: ignore[misc]
        latency = round((time.monotonic() - redis_start) * 1000, 2)
        components.append(ComponentHealth(name="redis", status="up", latency_ms=latency))
    except Exception:
        components.append(ComponentHealth(name="redis", status="down"))
        down_count += 1

    # WebSocket
    components.append(
        ComponentHealth(
            name="websocket",
            status="up",
            detail=f"{manager.active_count} connections",
        )
    )

    # Claude CLI
    claude_available = shutil.which("claude") is not None
    components.append(
        ComponentHealth(
            name="claude_code",
            status="up" if claude_available else "down",
        )
    )

    # System metrics
    mem = psutil.virtual_memory()
    cpu = psutil.cpu_percent(interval=0.1)
    uptime_seconds = time.monotonic() - _START_TIME

    if down_count >= 2:
        status = "unhealthy"
    elif down_count == 1:
        status = "degraded"
    else:
        status = "healthy"

    return SystemHealth(
        status=status,
        uptime_seconds=round(uptime_seconds, 1),
        started_at=_START_DATETIME.isoformat(),
        cpu_percent=cpu,
        memory_percent=mem.percent,
        memory_used_mb=round(mem.used / (1024 * 1024), 1),
        components=components,
    )


def _build_agent_overview() -> AgentOverview:
    """Summarize agent fleet from in-memory registry."""
    from app.schemas.agent import AgentStatus

    agents_list = agent_registry.list_agents_sync()
    briefs: list[AgentBrief] = []
    online = 0
    offline = 0
    busy = 0

    for agent in agents_list:
        status = agent.get("status", "offline")
        if status == AgentStatus.ONLINE:
            online += 1
        elif status == AgentStatus.BUSY:
            busy += 1
        else:
            offline += 1

        resources_raw = agent.get("resources")
        resources: dict[str, object] = (
            resources_raw if isinstance(resources_raw, dict) else {}
        )
        briefs.append(
            AgentBrief(
                host_id=agent.get("host_id", ""),
                status=status,
                cpu_percent=resources.get("cpu_usage_percent", 0),
                memory_percent=resources.get("memory_usage_percent", 0),
                active_tasks=agent.get("active_tasks", 0),
                uptime_seconds=agent.get("uptime_seconds", 0),
            )
        )

    return AgentOverview(
        total=len(briefs),
        online=online,
        offline=offline,
        busy=busy,
        agents=briefs,
    )


async def _build_usage_overview() -> UsageOverview:
    """Get subscription usage summary from cached data."""
    try:
        from app.services.subscription_usage_service import subscription_usage_service

        usage_data = await subscription_usage_service.get_usage()
        total_messages = usage_data.today_usage.message_count + usage_data.total_messages_today
        return UsageOverview(
            subscription_type=usage_data.subscription_type,
            usage_percent=usage_data.usage_percent,
            daily_message_limit=usage_data.daily_message_limit,
            total_messages_today=total_messages,
            is_rate_limited=usage_data.is_rate_limited,
            warning_threshold_reached=usage_data.warning_threshold_reached,
            limit_exceeded=usage_data.limit_exceeded,
        )
    except Exception:
        logger.warning("monitoring_usage_fetch_failed", exc_info=True)
        return UsageOverview()


async def _build_pulse_summary(db: AsyncSession) -> PulseSummary | None:
    """Get latest pulse report summary."""
    try:
        from app.services.pulse_service import get_pulse_service

        pulse_svc = get_pulse_service()
        pulse = await pulse_svc.get_latest_pulse(db)
        if pulse is None:
            return None

        return PulseSummary(
            summary_text=pulse.summary_text or "",
            total_messages=pulse.total_messages or 0,
            total_cost_usd=pulse.total_cost_usd,
            report_date=pulse.report_date.isoformat() if pulse.report_date else "",
            risks=pulse.risks or [],
            suggestions=pulse.suggestions or [],
        )
    except Exception:
        logger.warning("monitoring_pulse_fetch_failed", exc_info=True)
        return None
