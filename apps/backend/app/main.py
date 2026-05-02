"""RafRaf Backend - FastAPI application entry point."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from app.api.middleware.rate_limit import RateLimitMiddleware
from app.api.middleware.request_logging import RequestLoggingMiddleware
from app.api.routes.agent_ws import router as agent_ws_router
from app.api.routes.agents import router as agents_router
from app.api.routes.auth import router as auth_router
from app.api.routes.backups import router as backups_router
from app.api.routes.conversations import router as conversations_router
from app.api.routes.files import router as files_router
from app.api.routes.health import router as health_router
from app.api.routes.notifications import router as notifications_router
from app.api.routes.proactive_notifications import router as proactive_notifications_router
from app.api.routes.projects import router as projects_router
from app.api.routes.tasks import router as tasks_router
from app.api.routes.webhooks import router as webhooks_router
from app.api.routes.websocket import router as websocket_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging
from app.core.metrics import render_metrics
from app.core.redis import redis_client
from app.core.telemetry import setup_tracing
from app.services.bridge_registry_service import bridge_registry

# URLs excluded from FastAPI tracing — health probes and the metrics
# endpoint (T2.2 will add /metrics) are too noisy and add no signal.
_OTEL_EXCLUDED_URLS = "health,metrics"

logger: structlog.stdlib.BoundLogger = structlog.get_logger()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: startup and shutdown events."""
    settings = get_settings()
    setup_logging(debug=settings.debug)
    # Tracing setup MUST happen before AsyncPGInstrumentor.instrument()
    # below — the instrumentor binds the current global TracerProvider at
    # call-time, so swapping it afterwards leaves the asyncpg hooks
    # pointing at a NoOpTracerProvider.
    setup_tracing()
    # asyncpg instrumentation is idempotent on a per-process basis; calling
    # it more than once (e.g. uvicorn --reload) is safe — the underlying
    # instrumentor short-circuits via its is_instrumented_by_opentelemetry
    # flag. The OTel package ships without inline type hints; the
    # ``opentelemetry.*`` ignore-missing-imports stanza in pyproject.toml
    # absorbs the import side, but the ``Call to untyped function`` mypy
    # error needs an explicit per-call ignore.
    AsyncPGInstrumentor().instrument()  # type: ignore[no-untyped-call]
    logger.info("app_starting", version=settings.app_version)
    await bridge_registry.start_stale_checker()
    usage_task = asyncio.create_task(_subscription_usage_loop())
    yield
    usage_task.cancel()
    await bridge_registry.stop_stale_checker()
    await redis_client.close()
    logger.info("app_shutting_down")


async def _subscription_usage_loop() -> None:
    """Periodically refresh subscription usage data (every 10 minutes)."""
    from app.services.subscription_usage_service import subscription_usage_service

    while True:
        try:
            await subscription_usage_service.refresh()
        except Exception as exc:
            logger.warning("subscription_usage_refresh_failed", exc_info=exc)
        await asyncio.sleep(600)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    application = FastAPI(
        title=settings.app_name,
        description="AI Project Supervisor - Backend API",
        version=settings.app_version,
        lifespan=lifespan,
    )

    # CORS middleware
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Rate limiting middleware (auth endpoints)
    application.add_middleware(RateLimitMiddleware)

    # Request logging middleware
    application.add_middleware(RequestLoggingMiddleware)

    # Exception handlers
    register_exception_handlers(application)

    # Routers
    application.include_router(health_router)
    application.include_router(auth_router)
    application.include_router(websocket_router)
    application.include_router(agent_ws_router)
    application.include_router(agents_router)
    application.include_router(webhooks_router)
    application.include_router(conversations_router)
    application.include_router(projects_router)
    application.include_router(files_router)
    application.include_router(notifications_router)
    application.include_router(proactive_notifications_router)
    application.include_router(backups_router)
    application.include_router(tasks_router)

    # FastAPI auto-instrumentation — emits a server span per request,
    # propagating W3C tracecontext headers so the bridge (T2.1 Part B)
    # can stitch into the same trace. /health and /metrics are excluded
    # so the trace volume stays signal-rich.
    FastAPIInstrumentor.instrument_app(application, excluded_urls=_OTEL_EXCLUDED_URLS)

    return application


app = create_app()
