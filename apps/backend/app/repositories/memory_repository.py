"""Repository for ProjectMemory database operations."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import String, delete, func, or_, select, type_coerce
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import ProjectMemory


class MemoryRepository:
    """Database access layer for project_memory table.

    Supports listing, UPSERT (insert on conflict update), search,
    stale detection, and deletion.
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
        now = datetime.now(tz=UTC)
        stmt = (
            pg_insert(ProjectMemory)
            .values(
                project_id=project_id,
                category=category,
                key=key,
                value=value,
                confidence=confidence,
                source=source,
                last_verified_at=now,
            )
            .on_conflict_do_update(
                constraint="uq_project_memory_pckey",
                set_={
                    "value": value,
                    "confidence": confidence,
                    "source": source,
                    "last_verified_at": now,
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

    async def search(
        self,
        project_id: uuid.UUID,
        query: str | None = None,
        category: str | None = None,
        min_confidence: float = 0.0,
    ) -> list[ProjectMemory]:
        """Search project memories with text query and filters.

        Searches in key (ILIKE) and value JSONB (cast to text, ILIKE).

        Args:
            project_id: Project UUID.
            query: Optional text query (searches key and value).
            category: Optional category filter.
            min_confidence: Minimum confidence threshold.

        Returns:
            List of matching ProjectMemory rows.
        """
        stmt = select(ProjectMemory).where(
            ProjectMemory.project_id == project_id,
            ProjectMemory.confidence >= min_confidence,
        )
        if category:
            stmt = stmt.where(ProjectMemory.category == category)
        if query:
            pattern = f"%{query}%"
            stmt = stmt.where(
                or_(
                    ProjectMemory.key.ilike(pattern),
                    type_coerce(ProjectMemory.value, String).ilike(pattern),
                )
            )
        stmt = stmt.order_by(ProjectMemory.confidence.desc(), ProjectMemory.updated_at.desc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_stale_entries(
        self,
        project_id: uuid.UUID,
        days_threshold: int = 30,
    ) -> list[ProjectMemory]:
        """Find stale project memory entries.

        An entry is stale if last_verified_at is older than the threshold
        or if last_verified_at is NULL.

        Args:
            project_id: Project UUID.
            days_threshold: Number of days to consider stale.

        Returns:
            List of stale ProjectMemory rows.
        """
        cutoff = datetime.now(tz=UTC) - timedelta(days=days_threshold)
        stmt = select(ProjectMemory).where(
            ProjectMemory.project_id == project_id,
            or_(
                ProjectMemory.last_verified_at.is_(None),
                ProjectMemory.last_verified_at < cutoff,
            ),
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def delete_stale_entries(
        self,
        project_id: uuid.UUID,
        days_threshold: int = 30,
    ) -> int:
        """Delete stale project memory entries.

        Args:
            project_id: Project UUID.
            days_threshold: Number of days to consider stale.

        Returns:
            Number of deleted rows.
        """
        cutoff = datetime.now(tz=UTC) - timedelta(days=days_threshold)
        stmt = (
            delete(ProjectMemory)
            .where(
                ProjectMemory.project_id == project_id,
                or_(
                    ProjectMemory.last_verified_at.is_(None),
                    ProjectMemory.last_verified_at < cutoff,
                ),
            )
            .returning(ProjectMemory.id)
        )
        result = await self._session.execute(stmt)
        return len(list(result.scalars().all()))

    async def count_stale_entries(
        self,
        project_id: uuid.UUID,
        days_threshold: int = 30,
    ) -> int:
        """Count stale entries for a project.

        Args:
            project_id: Project UUID.
            days_threshold: Number of days to consider stale.

        Returns:
            Number of stale entries.
        """
        cutoff = datetime.now(tz=UTC) - timedelta(days=days_threshold)
        stmt = (
            select(func.count())
            .select_from(ProjectMemory)
            .where(
                ProjectMemory.project_id == project_id,
                or_(
                    ProjectMemory.last_verified_at.is_(None),
                    ProjectMemory.last_verified_at < cutoff,
                ),
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

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

    async def get_all_grouped_by_category(
        self,
        project_id: uuid.UUID,
    ) -> dict[str, list[ProjectMemory]]:
        """Get all memories grouped by category.

        Args:
            project_id: Project UUID.

        Returns:
            Dict with category keys and lists of ProjectMemory rows.
        """
        rows = await self.list_by_project(project_id)
        grouped: dict[str, list[ProjectMemory]] = {}
        for row in rows:
            if row.category not in grouped:
                grouped[row.category] = []
            grouped[row.category].append(row)
        return grouped

    async def verify_entry(
        self,
        memory_id: uuid.UUID,
        project_id: uuid.UUID,
    ) -> bool:
        """Update last_verified_at to current time.

        Args:
            memory_id: Memory UUID.
            project_id: Project UUID (for ownership validation).

        Returns:
            True if updated, False if not found.
        """
        row = await self.get_by_id(memory_id, project_id)
        if row is None:
            return False
        row.last_verified_at = datetime.now(tz=UTC)
        await self._session.flush()
        return True
