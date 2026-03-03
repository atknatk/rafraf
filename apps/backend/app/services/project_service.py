"""Project business logic service."""

import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.repositories.project_repo import ProjectRepository
from app.schemas.projects import (
    ProjectDetailResponse,
    ProjectListResponse,
    ProjectStatus,
    ProjectSummary,
)

logger: structlog.stdlib.BoundLogger = structlog.get_logger()


class ProjectService:
    """Proje business logic katmani."""

    def __init__(self, session: AsyncSession) -> None:
        self._repo = ProjectRepository(session)

    async def get_projects(
        self,
        status_filter: ProjectStatus | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> ProjectListResponse:
        """Proje listesini getirir."""
        filter_value = status_filter.value if status_filter is not None else None
        projects, total = await self._repo.get_projects(
            status_filter=filter_value,
            page=page,
            page_size=page_size,
        )

        summaries = [
            ProjectSummary(
                id=p.id,
                name=p.name,
                status=ProjectStatus(p.status),
                last_activity_at=p.last_activity_at,
                last_activity_summary=p.last_activity_summary,
                tech_stack=p.tech_stack,
            )
            for p in projects
        ]

        await logger.ainfo(
            "projects_listed",
            count=len(summaries),
            total=total,
            page=page,
        )

        return ProjectListResponse(
            projects=summaries,
            total=total,
            page=page,
            page_size=page_size,
        )

    async def get_project_by_id(
        self,
        project_id: uuid.UUID,
    ) -> ProjectDetailResponse:
        """Tek proje detayini getirir."""
        project = await self._repo.get_by_id(project_id)

        if project is None:
            raise NotFoundError(message=f"Project '{project_id}' not found")

        await logger.ainfo("project_detail_fetched", project_id=str(project_id))

        return ProjectDetailResponse(
            id=project.id,
            name=project.name,
            description=project.description,
            status=ProjectStatus(project.status),
            repository_url=project.repository_url,
            tech_stack=project.tech_stack,
            last_activity_at=project.last_activity_at,
            last_activity_summary=project.last_activity_summary,
            created_at=project.created_at.isoformat(),
            updated_at=project.updated_at.isoformat(),
        )
