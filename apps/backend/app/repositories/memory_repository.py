"""Repository for ProjectMemory database operations."""

import uuid

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import ProjectMemory


class MemoryRepository:
    """Database access layer for project_memory table.

    Supports listing, UPSERT (insert on conflict update), and deletion.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_project(
        self,
        project_id: uuid.UUID,
        category: str | None = None,
        key: str | None = None,
    ) -> list[ProjectMemory]:
        """List project memories with optional category/key filters.

        Args:
            project_id: Project UUID.
            category: Optional category filter.
            key: Optional key filter.

        Returns:
            List of matching ProjectMemory rows.
        """
        stmt = select(ProjectMemory).where(ProjectMemory.project_id == project_id)
        if category:
            stmt = stmt.where(ProjectMemory.category == category)
        if key:
            stmt = stmt.where(ProjectMemory.key == key)
        stmt = stmt.order_by(ProjectMemory.category, ProjectMemory.key)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def upsert(
        self,
        project_id: uuid.UUID,
        category: str,
        key: str,
        value: dict[str, object],
        confidence: float = 1.0,
        source: str = "user_stated",
    ) -> ProjectMemory:
        """Insert or update a project memory entry.

        Uses PostgreSQL ON CONFLICT ... DO UPDATE (UPSERT) on the
        (project_id, category, key) unique constraint.

        Args:
            project_id: Project UUID.
            category: Memory category.
            key: Memory key.
            value: JSONB value.
            confidence: Confidence score (0.0-1.0).
            source: Source indicator.

        Returns:
            The upserted ProjectMemory row.
        """
        stmt = (
            pg_insert(ProjectMemory)
            .values(
                project_id=project_id,
                category=category,
                key=key,
                value=value,
                confidence=confidence,
                source=source,
            )
            .on_conflict_do_update(
                constraint="uq_project_memory_pckey",
                set_={
                    "value": value,
                    "confidence": confidence,
                    "source": source,
                },
            )
            .returning(ProjectMemory)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def get_by_id(
        self,
        memory_id: uuid.UUID,
        project_id: uuid.UUID,
    ) -> ProjectMemory | None:
        """Get a single memory entry by ID and project_id.

        Args:
            memory_id: Memory UUID.
            project_id: Project UUID (for ownership validation).

        Returns:
            ProjectMemory if found, None otherwise.
        """
        stmt = select(ProjectMemory).where(
            ProjectMemory.id == memory_id,
            ProjectMemory.project_id == project_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def delete_by_id(
        self,
        memory_id: uuid.UUID,
        project_id: uuid.UUID,
    ) -> bool:
        """Delete a project memory entry by ID.

        Args:
            memory_id: Memory UUID.
            project_id: Project UUID (for ownership validation).

        Returns:
            True if deleted, False if not found.
        """
        stmt = (
            delete(ProjectMemory)
            .where(
                ProjectMemory.id == memory_id,
                ProjectMemory.project_id == project_id,
            )
            .returning(ProjectMemory.id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def get_project_summary(
        self,
        project_id: uuid.UUID,
    ) -> dict[str, dict[str, object]]:
        """Build a summary dict of all memories for a project.

        Groups memories by category, keyed by memory key.

        Args:
            project_id: Project UUID.

        Returns:
            Nested dict: {category: {key: value, ...}, ...}.
        """
        rows = await self.list_by_project(project_id)
        summary: dict[str, dict[str, object]] = {}
        for row in rows:
            if row.category not in summary:
                summary[row.category] = {}
            summary[row.category][row.key] = row.value
        return summary
