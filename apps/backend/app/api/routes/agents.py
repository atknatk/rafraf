"""REST endpoints for querying host agent status."""

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.routes.agent_ws import agent_manager, get_task_manager
from app.core.exceptions import NotFoundError
from app.schemas.agent import (
    AgentDetailResponse,
    AgentListResponse,
    AgentSettingsRequest,
    AgentStatus,
    AgentTaskListResponse,
    DispatchTaskRequest,
)
from app.schemas.agent_project import (
    AgentProcessesResponse,
    AgentProjectsResponse,
    AgentProjectSummary,
    AgentProjectUpdateRequest,
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


@router.get("/{host_id}/tasks", response_model=AgentTaskListResponse)
async def list_agent_tasks(
    host_id: str,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> AgentTaskListResponse:
    """Agent'in gorev gecmisini dondurur (son gorevler once)."""
    task_manager = get_task_manager()
    tasks = task_manager.list_tasks(host_id, limit=limit)
    pending_count = sum(1 for t in tasks if t.status in ("pending", "running"))
    return AgentTaskListResponse(
        tasks=tasks,
        total=len(tasks),
        pending_count=pending_count,
    )


@router.post("/{host_id}/tasks", response_model=AgentTaskListResponse)
async def dispatch_agent_task(
    host_id: str,
    body: DispatchTaskRequest,
) -> AgentTaskListResponse:
    """Agent'a yeni bir gorev gonder ve guncellenmis gorev listesini dondur."""
    task_manager = get_task_manager()
    detail = await agent_registry.get_agent(host_id)
    if detail is None:
        raise NotFoundError(message=f"Agent '{host_id}' not found")
    import asyncio

    asyncio.create_task(
        task_manager.dispatch(
            host_id=host_id,
            runner=body.runner,
            action=body.action,
            params=body.params,
            project_id=body.project_id,
        )
    )
    # Return current task list (task is now pending)
    tasks = task_manager.list_tasks(host_id, limit=50)
    pending_count = sum(1 for t in tasks if t.status in ("pending", "running"))
    return AgentTaskListResponse(
        tasks=tasks,
        total=len(tasks),
        pending_count=pending_count,
    )


@router.patch("/{host_id}/settings", response_model=AgentDetailResponse)
async def update_agent_settings(
    host_id: str,
    body: AgentSettingsRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AgentDetailResponse:
    """Agent ayarlarini guncelle ve agent'a config_update mesaji gonder."""
    from app.repositories.host_agent_repo import HostAgentRepository

    # DB'ye yaz
    repo = HostAgentRepository(session)
    updated = await repo.update_settings(
        host_id,
        dangerously_skip_permissions=body.dangerously_skip_permissions,
    )
    if not updated:
        raise NotFoundError(message=f"Agent '{host_id}' not found")
    await session.commit()

    # In-memory guncelle
    await agent_registry.update_skip_permissions(host_id, body.dangerously_skip_permissions)

    # Agent online ise WS config_update gonder
    connection_id = agent_registry.get_connection_id(host_id)
    if connection_id is not None:
        msg = {
            "type": "config_update",
            "dangerously_skip_permissions": body.dangerously_skip_permissions,
        }
        await agent_manager.send_json(connection_id, msg)
        await logger.ainfo(
            "agent_config_update_sent",
            host_id=host_id,
            dangerously_skip_permissions=body.dangerously_skip_permissions,
        )

    detail = await agent_registry.get_agent(host_id)
    if detail is None:
        raise NotFoundError(message=f"Agent '{host_id}' not found")
    return detail


@router.post("/{host_id}/projects/rescan", status_code=202)
async def rescan_agent_projects(host_id: str) -> dict[str, str]:
    """Agent'a bagli projeleri yeniden tarar (rescan komutu gonderir)."""
    record = agent_registry.get_connection_id(host_id)
    if record is None:
        raise NotFoundError(message=f"Agent '{host_id}' not connected")
    msg = {"type": "rescan_projects", "request_id": str(uuid.uuid4())}
    await agent_manager.send_json(record, msg)
    await logger.ainfo("rescan_projects_requested", host_id=host_id)
    return {"status": "rescan_requested", "host_id": host_id}


@router.delete("/{host_id}/tasks/{task_id}", status_code=204)
async def cancel_agent_task(host_id: str, task_id: str) -> None:  # noqa: ARG001
    """Bekleyen veya calisan bir gorevi iptal et."""
    task_manager = get_task_manager()
    cancelled = task_manager.cancel(task_id)
    if not cancelled:
        raise NotFoundError(
            message=f"Task '{task_id}' not found or already completed"
        )
