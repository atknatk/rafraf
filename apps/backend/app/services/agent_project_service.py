"""Agent-proje iliski yonetim servisi."""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_project import AgentProject
from app.models.project import Project
from app.schemas.agent_project import AgentProjectsResponse, AgentProjectSummary

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
        """Proje-agent iliskisini ekler (pasif olarak).

        Agent project_sync yaptiginda cagrilir.
        Yeni iliski is_active=False ile baslatilir; kullanici aktif yapana kadar
        chat picker'da gozukmez. Zaten varsa mevcut is_active degeri korunur.
        """
        stmt = (
            pg_insert(AgentProject)
            .values(
                agent_id=agent_id,
                project_id=project_id,
                is_active=False,
            )
            .on_conflict_do_nothing(constraint="uq_agent_project")
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
            local_path=project.local_path,
            tech_stack=list(project.tech_stack),
        )

    async def sync_and_archive_removed(
        self,
        agent_id: str,
        synced_project_ids: set[uuid.UUID],
    ) -> int:
        """Agent sync'ten artik gelmeyen agent_scan projelerini archived yapar.

        Sadece source='agent_scan' olan projeler etkilenir; manuel projeler dokunulmaz.

        Returns:
            Archive edilen proje sayisi.
        """
        # Bu agent'a bagli tum proje ID'lerini getir
        linked_result = await self._session.execute(
            select(AgentProject.project_id).where(AgentProject.agent_id == agent_id)
        )
        all_linked_ids: set[uuid.UUID] = {row[0] for row in linked_result.all()}

        removed_ids = all_linked_ids - synced_project_ids
        if not removed_ids:
            return 0

        # Sadece agent_scan kaynakli ve henuz archived olmayanlari bul
        proj_result = await self._session.execute(
            select(Project).where(
                Project.id.in_(removed_ids),
                Project.source == "agent_scan",
                Project.status != "archived",
            )
        )
        removed_projects = proj_result.scalars().all()

        archived_count = 0
        for project in removed_projects:
            project.status = "archived"
            archived_count += 1

        if archived_count:
            await self._session.flush()
            logger.info(
                "agent_scan_projects_archived",
                agent_id=agent_id,
                count=archived_count,
            )

        return archived_count

    async def get_all_agents_projects(self) -> list[AgentProjectsResponse]:
        """Tum agent-proje iliskilerini DB'den tek sorguda getirir.

        Agent'in online olmasina gerek yok; agent_projects tablosundaki
        tum kayitlari agent bazinda gruplar.
        """
        result = await self._session.execute(
            select(AgentProject, Project)
            .join(Project, AgentProject.project_id == Project.id)
            .where(Project.status != "archived")
            .order_by(AgentProject.agent_id, Project.name)
        )
        rows = result.all()

        grouped: dict[str, list[AgentProjectSummary]] = {}
        for ap, project in rows:
            summary = AgentProjectSummary(
                project_id=ap.project_id,
                project_name=project.name,
                is_active=ap.is_active,
                repository_url=project.repository_url,
                local_path=project.local_path,
                tech_stack=list(project.tech_stack),
            )
            grouped.setdefault(ap.agent_id, []).append(summary)

        return [
            AgentProjectsResponse(agent_id=agent_id, projects=projects, total=len(projects))
            for agent_id, projects in grouped.items()
        ]

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
                local_path=project.local_path,
                tech_stack=list(project.tech_stack),
            )
            for ap, project in rows
        ]

        return AgentProjectsResponse(
            agent_id=agent_id,
            projects=summaries,
            total=len(summaries),
        )
