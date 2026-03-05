"""REST endpoints for querying host agent status."""

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.exceptions import NotFoundError
from app.schemas.agent import AgentDetailResponse, AgentListResponse, AgentStatus
from app.schemas.agent_project import (
    AgentProjectsResponse,
    AgentProjectUpdateRequest,
    AgentProcessesResponse,
    AgentProjectSummary,
)
from app.services.agent_project_service import AgentProjectService
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


@router.get("/all-linked-projects", response_model=list[AgentProjectsResponse])
async def list_all_agent_projects(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[AgentProjectsResponse]:
    """Tum agentlara bagli projeleri DB'den getirir (agent online olmak zorunda degil)."""
    service = AgentProjectService(session)
    return await service.get_all_agents_projects()


@router.get("/{host_id}", response_model=AgentDetailResponse)
async def get_agent(host_id: str) -> AgentDetailResponse:
    """Return details for a single agent identified by host_id."""
    detail = await agent_registry.get_agent(host_id)
    if detail is None:
        raise NotFoundError(message=f"Agent '{host_id}' not found")
    return detail


@router.get("/{host_id}/projects", response_model=AgentProjectsResponse)
async def list_agent_projects(
    host_id: str,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AgentProjectsResponse:
    """Agent'a bagli projeleri listeler (aktif/pasif bilgisi ile)."""
    service = AgentProjectService(session)
    return await service.get_projects_for_agent(host_id)


@router.patch(
    "/{host_id}/projects/{project_id}",
    response_model=AgentProjectSummary,
)
async def update_agent_project(
    host_id: str,
    project_id: uuid.UUID,
    body: AgentProjectUpdateRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AgentProjectSummary:
    """Agent'taki bir projeyi aktif/pasif yapar."""
    service = AgentProjectService(session)
    result = await service.set_project_active(host_id, project_id, body.is_active)
    if result is None:
        raise NotFoundError(
            message=f"Agent '{host_id}' icin proje '{project_id}' bulunamadi"
        )
    await session.commit()
    return result


@router.get("/{host_id}/processes", response_model=AgentProcessesResponse)
async def get_agent_processes(host_id: str) -> AgentProcessesResponse:
    """Agent'ta calisan claude process listesini dondurur."""
    processes = agent_registry.get_claude_processes(host_id)
    return AgentProcessesResponse(
        agent_id=host_id,
        processes=processes,
        total=len(processes),
    )
