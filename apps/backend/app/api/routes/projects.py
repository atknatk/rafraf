"""REST endpoints for project management."""

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.projects import (
    ProjectDetailResponse,
    ProjectListResponse,
    ProjectStatus,
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
    page: Annotated[
        int,
        Query(ge=1, description="Sayfa numarasi"),
    ] = 1,
    page_size: Annotated[
        int,
        Query(ge=1, le=100, description="Sayfa basina proje sayisi"),
    ] = 20,
) -> ProjectListResponse:
    """Return paginated project list, optionally filtered by status."""
    service = ProjectService(session)
    return await service.get_projects(
        status_filter=status,
        page=page,
        page_size=page_size,
    )


@router.get("/{project_id}", response_model=ProjectDetailResponse)
async def get_project(
    project_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ProjectDetailResponse:
    """Return details for a single project identified by project_id."""
    service = ProjectService(session)
    return await service.get_project_by_id(project_id)
