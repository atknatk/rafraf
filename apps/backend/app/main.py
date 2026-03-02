"""RafRaf Backend - FastAPI application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.middleware.rate_limit import RateLimitMiddleware
from app.api.middleware.request_logging import RequestLoggingMiddleware
from app.api.routes.agent_ws import router as agent_ws_router
from app.api.routes.agents import router as agents_router
from app.api.routes.auth import router as auth_router
from app.api.routes.health import router as health_router
from app.api.routes.webhooks import router as webhooks_router
from app.api.routes.websocket import router as websocket_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging
from app.services.agent_registry_service import agent_registry

logger: structlog.stdlib.BoundLogger = structlog.get_logger()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: startup and shutdown events."""
    settings = get_settings()
    setup_logging(debug=settings.debug)
    await logger.ainfo("app_starting", version=settings.app_version)
    await agent_registry.start_stale_checker()
    yield
    await agent_registry.stop_stale_checker()
    await logger.ainfo("app_shutting_down")


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

    return application


app = create_app()
