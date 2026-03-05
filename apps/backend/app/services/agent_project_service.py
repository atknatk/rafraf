"""Agent-proje iliski yonetim servisi."""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_project import AgentProject
from app.models.project import Project
from app.schemas.agent_project import AgentProjectSummary, AgentProjectsResponse

logger: structlog.stdlib.BoundLogger = structlog.get_logger()


class AgentProjectService:
    """Agent-proje iliskisini yonetir: linkleme, aktiflik toggling."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def link_project_to_agent(
        self,
        agent_id: str,
        project_id: uuid.UUID,
    ) -> None:
        """Proje-agent iliskisini ekler veya gunceller (is_active=True).

        Agent project_sync yaptiginda cagrilir.
        """
        stmt = (
            pg_insert(AgentProject)
            .values(
                agent_id=agent_id,
                project_id=project_id,
                is_active=True,
            )
            .on_conflict_do_update(
                constraint="uq_agent_project",
                set_={"is_active": True},
            )
        )
        await self._session.execute(stmt)
        logger.info("agent_project_linked", agent_id=agent_id, project_id=str(project_id))

    async def set_project_active(
        self,
        agent_id: str,
        project_id: uuid.UUID,
        is_active: bool,
    ) -> AgentProjectSummary | None:
        """Proje-agent iliski aktifligini degistirir."""
        result = await self._session.execute(
            select(AgentProject, Project)
            .join(Project, AgentProject.project_id == Project.id)
            .where(
                AgentProject.agent_id == agent_id,
                AgentProject.project_id == project_id,
            )
        )
        row = result.first()
        if row is None:
            return None

        ap, project = row
        ap.is_active = is_active
        await self._session.flush()

        logger.info(
            "agent_project_active_changed",
            agent_id=agent_id,
            project_id=str(project_id),
            is_active=is_active,
        )
        return AgentProjectSummary(
            project_id=ap.project_id,
            project_name=project.name,
            is_active=ap.is_active,
            repository_url=project.repository_url,
            tech_stack=list(project.tech_stack),
        )

    async def get_projects_for_agent(self, agent_id: str) -> AgentProjectsResponse:
        """Agent'a bagli tum projeleri dondurur."""
        result = await self._session.execute(
            select(AgentProject, Project)
            .join(Project, AgentProject.project_id == Project.id)
            .where(AgentProject.agent_id == agent_id)
            .order_by(Project.name)
        )
        rows = result.all()

        summaries = [
            AgentProjectSummary(
                project_id=ap.project_id,
                project_name=project.name,
                is_active=ap.is_active,
                repository_url=project.repository_url,
                tech_stack=list(project.tech_stack),
            )
            for ap, project in rows
        ]

        return AgentProjectsResponse(
            agent_id=agent_id,
            projects=summaries,
            total=len(summaries),
        )
