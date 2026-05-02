"""Health, liveness and readiness check endpoints.

Three endpoints are exposed:

* ``/health`` — Kubernetes-style **liveness** probe. Returns 200 with a tiny
  static payload as long as the process is alive. Performs **no** external
  dependency calls so a flaky dependency cannot cause kube to kill the pod.
* ``/ready`` — Kubernetes-style **readiness** probe. Verifies critical
  dependencies (DB ``SELECT 1``, Redis ``PING``, optional bridge presence)
  with short timeouts. Returns 503 + per-check booleans when any required
  dependency is unhealthy, 200 otherwise.
* ``/api/v1/health/detailed`` — Operator-facing rich health snapshot used by
  the dashboard / monitoring scripts. Always returns 200 (even on partial
  outage) and reports per-component status + latency.

All three endpoints are intentionally **unauthenticated** — Kubernetes/ALB
probes do not carry credentials, and the detailed view is read-only.
"""

import asyncio
import shutil
import time
from datetime import UTC, datetime
from typing import Annotated

import psutil
import structlog
from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.routes.websocket import manager
from app.core.config import get_settings
from app.core.redis import redis_client
from app.schemas.health import HealthResponse
from app.services.bridge_registry_service import bridge_registry

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

router = APIRouter(tags=["health"])

# Module-level startup time for uptime calculation
_START_TIME: float = time.monotonic()
_START_DATETIME: datetime = datetime.now(tz=UTC)

# Per-check timeout for readiness probes. Probes run on the hot path of
# Kubernetes (every few seconds) so we keep these very tight to avoid
# blocking the event loop on a misbehaving dependency.
_READY_CHECK_TIMEOUT_SECONDS: float = 1.0


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Liveness probe — returns 200 as long as the process is alive.

    Per Doc 10 §8 (Faz 2), this endpoint MUST NOT touch external dependencies
    so that a transient DB/Redis outage does not cause Kubernetes to restart
    a healthy pod. Use ``/ready`` for dependency-aware readiness checks and
    ``/api/v1/health/detailed`` for operator-facing diagnostics.
    """
    settings = get_settings()
    return {
        "status": "ok",
        "service": "rafraf-backend",
        "version": settings.app_version,
    }


# Backwards-compatible alias for callers (and the existing TestClient in
# /api/v1/health/detailed tests) that expect a Pydantic-validated body.
@router.get("/healthz", response_model=HealthResponse)
async def healthz() -> HealthResponse:
    """Alias of ``/health`` returning the strict Pydantic model.

    Some monitoring stacks key on the ``/healthz`` convention. We keep both
    paths to avoid forcing a config change in any deployment.
    """
    settings = get_settings()
    return HealthResponse(status="ok", version=settings.app_version)


async def _check_db(db: AsyncSession) -> bool:
    """Execute ``SELECT 1`` with a tight timeout. ``True`` if the DB responds.

    Catches a broad ``Exception`` deliberately: drivers raise a wide variety
    of exception types (``OperationalError``, ``InterfaceError``,
    ``DBAPIError``…) and a readiness probe must aggregate all failure modes
    into a single boolean rather than propagating.
    """
    try:
        await asyncio.wait_for(
            db.execute(text("SELECT 1")),
            timeout=_READY_CHECK_TIMEOUT_SECONDS,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("ready_db_check_failed", exc_info=exc)
        return False
    return True


async def _ping_redis_client() -> None:
    """Issue ``PING`` against the shared Redis client.

    Wrapped in a helper because ``redis-py``'s async stubs declare
    ``ping`` as ``Awaitable[bool] | bool`` (it is sync-or-async depending
    on backend), which breaks ``asyncio.wait_for`` typing if invoked
    inline. The helper hides that polymorphism behind a clean coroutine.
    """
    client = await redis_client._get_client()
    await client.ping()  # type: ignore[misc]


async def _check_redis() -> bool:
    """Ping Redis with a tight timeout. ``True`` if PONG received."""
    try:
        await asyncio.wait_for(
            _ping_redis_client(),
            timeout=_READY_CHECK_TIMEOUT_SECONDS,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("ready_redis_check_failed", exc_info=exc)
        return False
    return True


async def _check_bridge_online() -> bool:
    """``True`` if at least one registered bridge is online.

    Uses the in-process ``BridgeRegistryService`` snapshot — no IO is
    performed so this check is essentially free.
    """
    try:
        result = await bridge_registry.list_agents()
    except Exception as exc:  # noqa: BLE001
        logger.warning("ready_bridge_check_failed", exc_info=exc)
        return False
    return result.online_count > 0


@router.get("/ready")
async def ready_check(
    db: Annotated[AsyncSession, Depends(get_db)],
    response: Response,
) -> dict[str, object]:
    """Readiness probe — 200 only when all required dependencies are healthy.

    Returns 503 with a structured payload identifying which checks failed so
    operators can debug from probe logs. Required checks:

    * ``db`` — PostgreSQL responsive to ``SELECT 1``
    * ``redis`` — Redis responsive to ``PING``
    * ``bridge`` — at least one bridge online (only when
      ``READY_REQUIRES_BRIDGE=true``; defaults to false so bare-startup
      readiness succeeds before any bridge has connected)
    """
    settings = get_settings()

    # Run independent checks concurrently to keep the probe fast.
    db_ok, redis_ok, bridge_ok = await asyncio.gather(
        _check_db(db),
        _check_redis(),
        _check_bridge_online(),
    )

    checks: dict[str, bool] = {
        "db": db_ok,
        "redis": redis_ok,
        "bridge": bridge_ok,
    }

    required_failed = (not db_ok) or (not redis_ok)
    if settings.ready_requires_bridge and not bridge_ok:
        required_failed = True

    if required_failed:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "not_ready", "checks": checks}

    return {"status": "ready", "checks": checks}


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
