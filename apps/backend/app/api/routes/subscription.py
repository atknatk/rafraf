"""REST endpoints for subscription usage tracking."""

from __future__ import annotations

import structlog
from fastapi import APIRouter

from app.schemas.subscription import SubscriptionUsageResponse
from app.services.subscription_usage_service import subscription_usage_service

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/subscription", tags=["subscription"])


@router.get("/usage", response_model=SubscriptionUsageResponse)
async def get_subscription_usage() -> SubscriptionUsageResponse:
    """Return cached subscription usage data."""
    return await subscription_usage_service.get_usage()


@router.post("/usage/refresh", response_model=SubscriptionUsageResponse)
async def refresh_subscription_usage() -> SubscriptionUsageResponse:
    """Force-refresh subscription usage data."""
    return await subscription_usage_service.refresh()
