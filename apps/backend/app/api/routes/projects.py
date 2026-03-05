"""REST endpoints for project management."""

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.api.deps import get_db
from app.schemas.projects import (
    DeduplicateResponse,
    ProjectCreateRequest,
    ProjectCreateResponse,
    ProjectDetailResponse,
    ProjectListResponse,
    ProjectStatus,
    ProjectStatusUpdateRequest,
    ProjectUpdateRequest,
)
from app.services.project_service import ProjectService

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


@router.get("", response_model=ProjectListResponse)
async def list_projects(
    session: Annotated[AsyncSession, Depends(get_db)],
    status: Annotated[
        ProjectStatus | None,
        Query(description="Proje durumuna gore filtrele"),
    ] = None,
    agent_id: Annotated[
        str | None,
        Query(description="Agent'a gore filtrele (agent host_id)"),
    ] = None,
    page: Annotated[
        int,
        Query(ge=1, description="Sayfa numarasi"),
    ] = 1,
    page_size: Annotated[
        int,
        Query(ge=1, le=100, description="Sayfa basina proje sayisi"),
    ] = 20,
) -> ProjectListResponse:
    """Return paginated project list, optionally filtered by status and/or agent."""
    service = ProjectService(session)
    return await service.get_projects(
        status_filter=status,
        agent_id=agent_id,
        page=page,
        page_size=page_size,
    )


@router.post("/deduplicate", response_model=DeduplicateResponse)
async def deduplicate_projects(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> DeduplicateResponse:
    """Delete duplicate projects (same local_path or repository_url).

    Keeps the most recently updated record. Messages are SET NULL, agent_project
    links are CASCADE deleted. Safe to call multiple times (idempotent).
    """
    service = ProjectService(session)
    result = await service.deduplicate_projects()
    await session.commit()
    return result


@router.post(
    "",
    response_model=ProjectCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_project(
    body: ProjectCreateRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ProjectCreateResponse:
    """Create a new project."""
    service = ProjectService(session)
    return await service.create_project(body)


@router.put("/{project_id}", response_model=ProjectDetailResponse)
async def update_project(
    project_id: uuid.UUID,
    body: ProjectUpdateRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ProjectDetailResponse:
    """Update an existing project."""
    service = ProjectService(session)
    return await service.update_project(project_id, body)


@router.get("/{project_id}", response_model=ProjectDetailResponse)
async def get_project(
    project_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ProjectDetailResponse:
    """Return details for a single project identified by project_id."""
    service = ProjectService(session)
    return await service.get_project_by_id(project_id)


@router.patch("/{project_id}/status", response_model=ProjectDetailResponse)
async def update_project_status(
    project_id: uuid.UUID,
    body: ProjectStatusUpdateRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ProjectDetailResponse:
    """Update only the status field of a project (active / pending / completed / archived)."""
    service = ProjectService(session)
    return await service.update_project_status(project_id, body)
