"""Health check endpoints."""

import shutil
import time
from datetime import UTC, datetime
from typing import Annotated

import psutil
import structlog
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.routes.websocket import manager
from app.core.config import get_settings
from app.core.redis import redis_client
from app.schemas.health import HealthResponse

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

router = APIRouter(tags=["health"])

# Module-level startup time for uptime calculation
_START_TIME: float = time.monotonic()
_START_DATETIME: datetime = datetime.now(tz=UTC)


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Return application health status."""
    settings = get_settings()
    return HealthResponse(status="ok", version=settings.app_version)


@router.get("/api/v1/health/detailed")
async def detailed_health(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, object]:
    """Detaylı sistem sağlık bilgisi döner.

    Tüm componentler auth gerektirmeden erişilebilir (monitoring için).
    DB/Redis hata verirse component status "down" yazar, endpoint yine 200 döner.
    """
    components: dict[str, object] = {}
    down_count = 0

    # --- Database ---
    db_start = time.monotonic()
    try:
        await db.execute(text("SELECT 1"))
        db_latency_ms = (time.monotonic() - db_start) * 1000
        components["database"] = {"status": "up", "latency_ms": round(db_latency_ms, 2)}
    except Exception as exc:
        logger.warning("health_db_check_failed", exc_info=exc)
        components["database"] = {"status": "down", "latency_ms": None}
        down_count += 1

    # --- Redis ---
    redis_start = time.monotonic()
    try:
        client = await redis_client._get_client()
        await client.ping()  # type: ignore[misc]
        redis_latency_ms = (time.monotonic() - redis_start) * 1000
        components["redis"] = {"status": "up", "latency_ms": round(redis_latency_ms, 2)}
    except Exception as exc:
        logger.warning("health_redis_check_failed", exc_info=exc)
        components["redis"] = {"status": "down", "latency_ms": None}
        down_count += 1

    # --- WebSocket connections ---
    components["websocket"] = {"active_connections": manager.active_count}

    # --- System metrics ---
    mem = psutil.virtual_memory()
    cpu_percent = psutil.cpu_percent(interval=0.1)
    components["system"] = {
        "memory_percent": mem.percent,
        "memory_used_mb": round(mem.used / (1024 * 1024), 1),
        "cpu_percent": cpu_percent,
    }

    # --- Claude Code binary ---
    claude_available = shutil.which("claude") is not None
    components["claude_code"] = {"available": claude_available}

    # --- Uptime ---
    uptime_seconds = time.monotonic() - _START_TIME
    components["uptime"] = {
        "started_at": _START_DATETIME.isoformat(),
        "uptime_seconds": round(uptime_seconds, 1),
    }

    # --- Overall status ---
    if down_count >= 2:
        overall_status = "unhealthy"
    elif down_count == 1:
        overall_status = "degraded"
    else:
        overall_status = "healthy"

    return {
        "status": overall_status,
        "timestamp": datetime.now(tz=UTC).isoformat(),
        "components": components,
    }
