"""RafRaf Backend - FastAPI application entry point."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.middleware.rate_limit import RateLimitMiddleware
from app.api.middleware.request_logging import RequestLoggingMiddleware
from app.api.routes.agent_ws import router as agent_ws_router
from app.api.routes.agents import router as agents_router
from app.api.routes.analytics import router as analytics_router
from app.api.routes.auth import router as auth_router
from app.api.routes.backups import router as backups_router
from app.api.routes.conversation_memory import router as conversation_memory_router
from app.api.routes.conversations import router as conversations_router
from app.api.routes.cost import router as cost_router
from app.api.routes.cost_alerts import router as cost_alerts_router
from app.api.routes.files import router as files_router
from app.api.routes.health import router as health_router
from app.api.routes.maestro import router as maestro_router
from app.api.routes.memory import router as memory_router
from app.api.routes.notifications import router as notifications_router
from app.api.routes.personal_memory import router as personal_memory_router
from app.api.routes.proactive_notifications import router as proactive_notifications_router
from app.api.routes.projects import router as projects_router
from app.api.routes.pulse import router as pulse_router
from app.api.routes.subscription import router as subscription_router
from app.api.routes.webhooks import router as webhooks_router
from app.api.routes.websocket import router as websocket_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging
from app.core.redis import redis_client
from app.services.agent_registry_service import agent_registry

logger: structlog.stdlib.BoundLogger = structlog.get_logger()


def _register_host_agent_tool() -> None:
    """Register the HostAgentTool with the global tool registry.

    Called at startup after agent_manager and agent_registry are available.
    """
    from app.api.routes.agent_ws import get_task_manager
    from app.services.orchestrator_service import get_tool_registry
    from app.tools.host_agent_tool import HostAgentTool

    registry = get_tool_registry()
    task_manager = get_task_manager()
    tool = HostAgentTool(
        task_manager=task_manager,
        agent_registry=agent_registry,
    )
    tool.register(registry)
    logger.info("host_agent_tool_registered", tool_count=registry.tool_count)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: startup and shutdown events."""
    settings = get_settings()
    setup_logging(debug=settings.debug)
    logger.info("app_starting", version=settings.app_version)
    await agent_registry.start_stale_checker()
    _register_host_agent_tool()
    usage_task = asyncio.create_task(_subscription_usage_loop())
    yield
    usage_task.cancel()
    await agent_registry.stop_stale_checker()
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
    application.include_router(memory_router)
    application.include_router(conversations_router)  # /history, /missed — must be before conversation_memory
    application.include_router(conversation_memory_router)  # /{session_id} catch-all
    application.include_router(projects_router)
    application.include_router(cost_router)
    application.include_router(files_router)
    application.include_router(notifications_router)
    application.include_router(proactive_notifications_router)
    application.include_router(personal_memory_router)
    application.include_router(maestro_router)
    application.include_router(subscription_router)
    application.include_router(pulse_router)
    application.include_router(analytics_router)
    application.include_router(cost_alerts_router)
    application.include_router(backups_router)

    return application


app = create_app()
