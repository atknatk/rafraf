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
