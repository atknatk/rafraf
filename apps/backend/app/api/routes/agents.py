"""REST endpoints for querying host agent status."""

from typing import Annotated

import structlog
from fastapi import APIRouter, Query

from app.core.exceptions import NotFoundError
from app.schemas.agent import AgentDetailResponse, AgentListResponse, AgentStatus
from app.services.agent_registry_service import agent_registry

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])


@router.get("", response_model=AgentListResponse)
async def list_agents(
    status: Annotated[
        AgentStatus | None,
        Query(description="Agent durumuna gore filtrele"),
    ] = None,
) -> AgentListResponse:
    """Return all registered agents, optionally filtered by status."""
    return await agent_registry.list_agents(status_filter=status)


@router.get("/{host_id}", response_model=AgentDetailResponse)
async def get_agent(host_id: str) -> AgentDetailResponse:
    """Return details for a single agent identified by host_id."""
    detail = await agent_registry.get_agent(host_id)
    if detail is None:
        raise NotFoundError(message=f"Agent '{host_id}' not found")
    return detail
