"""Project repository — async database access layer."""

import uuid
from collections.abc import Sequence

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project

logger: structlog.stdlib.BoundLogger = structlog.get_logger()


class ProjectRepository:
    """Proje DB erisim katmani. Tum veritabani islemleri burada yapilir."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_projects(
        self,
        status_filter: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[Sequence[Project], int]:
        """Proje listesini filtre ve sayfalama ile getirir.

        Returns:
            Tuple of (project list, total count).
        """
        query = select(Project)
        count_query = select(func.count()).select_from(Project)

        if status_filter is not None:
            query = query.where(Project.status == status_filter)
            count_query = count_query.where(Project.status == status_filter)

        # Total count
        total_result = await self._session.execute(count_query)
        total = total_result.scalar_one()

        # Paginated results
        offset = (page - 1) * page_size
        query = query.order_by(Project.created_at.desc()).offset(offset).limit(page_size)
        result = await self._session.execute(query)
        projects = result.scalars().all()

        await logger.ainfo(
            "projects_fetched",
            count=len(projects),
            total=total,
            page=page,
            status_filter=status_filter,
        )

        return projects, total

    async def get_by_id(self, project_id: uuid.UUID) -> Project | None:
        """Tek proje getirir, bulunamazsa None dondurur."""
        query = select(Project).where(Project.id == project_id)
        result = await self._session.execute(query)
        project = result.scalar_one_or_none()

        if project is not None:
            await logger.ainfo("project_found", project_id=str(project_id))
        else:
            await logger.ainfo("project_not_found", project_id=str(project_id))

        return project

    async def create(
        self,
        *,
        name: str,
        description: str | None = None,
        status: str = "active",
        repository_url: str | None = None,
        local_path: str | None = None,
        tech_stack: list[str] | None = None,
        source: str = "manual",
    ) -> Project:
        """Yeni proje olusturur."""
        project = Project(
            name=name,
            description=description,
            status=status,
            repository_url=repository_url,
            local_path=local_path,
            tech_stack=tech_stack or [],
            source=source,
        )
        self._session.add(project)
        await self._session.flush()
        await self._session.refresh(project)
        await logger.ainfo("project_created", project_id=str(project.id), name=name)
        return project

    async def update(
        self,
        project: Project,
        **kwargs: object,
    ) -> Project:
        """Proje alanlarini gunceller."""
        for key, value in kwargs.items():
            if value is not None and hasattr(project, key):
                setattr(project, key, value)
        await self._session.flush()
        await self._session.refresh(project)
        await logger.ainfo("project_updated", project_id=str(project.id))
        return project

    async def get_by_repository_url(self, url: str) -> Project | None:
        """Repository URL ile proje arar (agent sync icin)."""
        query = select(Project).where(Project.repository_url == url)
        result = await self._session.execute(query)
        return result.scalar_one_or_none()
