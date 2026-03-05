"""Project business logic service."""

import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.project import Project
from app.repositories.project_repo import ProjectRepository
from app.schemas.projects import (
    ProjectCreateRequest,
    ProjectCreateResponse,
    ProjectDetailResponse,
    ProjectListResponse,
    ProjectStatus,
    ProjectStatusUpdateRequest,
    ProjectSummary,
    ProjectUpdateRequest,
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

        return self._to_detail_response(project)

    async def create_project(
        self,
        request: ProjectCreateRequest,
    ) -> ProjectCreateResponse:
        """Yeni proje olusturur."""
        project = await self._repo.create(
            name=request.name,
            description=request.description,
            status=request.status.value,
            repository_url=request.repository_url,
            local_path=request.local_path,
            tech_stack=request.tech_stack,
            source=request.source,
        )
        await logger.ainfo("project_created", project_id=str(project.id), name=project.name)
        return ProjectCreateResponse(
            id=project.id,
            name=project.name,
            status=ProjectStatus(project.status),
            created_at=project.created_at.isoformat(),
        )

    async def update_project(
        self,
        project_id: uuid.UUID,
        request: ProjectUpdateRequest,
    ) -> ProjectDetailResponse:
        """Proje bilgilerini gunceller."""
        project = await self._repo.get_by_id(project_id)
        if project is None:
            raise NotFoundError(message=f"Project '{project_id}' not found")

        updates = request.model_dump(exclude_none=True)
        if "status" in updates:
            updates["status"] = updates["status"].value
        project = await self._repo.update(project, **updates)

        await logger.ainfo("project_updated", project_id=str(project_id))
        return self._to_detail_response(project)

    async def update_project_status(
        self,
        project_id: uuid.UUID,
        request: ProjectStatusUpdateRequest,
    ) -> ProjectDetailResponse:
        """Proje durumunu gunceller."""
        project = await self._repo.get_by_id(project_id)
        if project is None:
            raise NotFoundError(message=f"Project '{project_id}' not found")

        project = await self._repo.update(project, status=request.status.value)
        await logger.ainfo(
            "project_status_updated",
            project_id=str(project_id),
            status=request.status.value,
        )
        return self._to_detail_response(project)

    async def upsert_from_agent(
        self,
        *,
        name: str,
        repository_url: str | None,
        tech_stack: list[str],
        source: str,
    ) -> ProjectDetailResponse:
        """Agent'tan gelen projeyi ekler veya gunceller (upsert by repo URL)."""
        existing = None
        if repository_url:
            existing = await self._repo.get_by_repository_url(repository_url)

        if existing:
            existing = await self._repo.update(
                existing,
                name=name,
                tech_stack=tech_stack,
                source=source,
            )
            await logger.ainfo("project_upserted_update", name=name)
            return self._to_detail_response(existing)

        project = await self._repo.create(
            name=name,
            repository_url=repository_url,
            tech_stack=tech_stack,
            source=source,
        )
        await logger.ainfo("project_upserted_create", name=name)
        return self._to_detail_response(project)

    @staticmethod
    def _to_detail_response(project: Project) -> ProjectDetailResponse:
        """Project model'i ProjectDetailResponse'a donusturur."""
        return ProjectDetailResponse(
            id=project.id,
            name=project.name,
            description=project.description,
            status=ProjectStatus(project.status),
            repository_url=project.repository_url,
            local_path=project.local_path,
            tech_stack=project.tech_stack,
            source=project.source,
            last_activity_at=project.last_activity_at,
            last_activity_summary=project.last_activity_summary,
            created_at=project.created_at.isoformat(),
            updated_at=project.updated_at.isoformat(),
        )
