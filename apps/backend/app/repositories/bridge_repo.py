"""Bridge repository — async database access layer.

Replaces the legacy ``host_agent_repo`` as part of the V1 production pivot
(docs/10 §6.1.1, T1.3). Persists the registry of registered Go bridges
(``bridges`` table; renamed from ``host_agents`` in alembic 014).
"""

from datetime import UTC, datetime

import structlog
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bridge import Bridge

logger: structlog.stdlib.BoundLogger = structlog.get_logger()


class BridgeRepository:
    """DB access layer for the ``bridges`` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_from_heartbeat(
        self,
        *,
        host_id: str,
        status: str = "online",
        capabilities: list[str] | None = None,
        hostname: str | None = None,
        os: str | None = None,
        os_version: str | None = None,
        arch: str | None = None,
        agent_version: str | None = None,
        connection_id: str | None = None,
        last_resources: dict[str, object] | None = None,
    ) -> Bridge:
        """Insert or update a bridge record on heartbeat."""
        now = datetime.now(tz=UTC)
        values: dict[str, object] = {
            "host_id": host_id,
            "status": status,
            "last_heartbeat_at": now,
        }
        if capabilities is not None:
            values["capabilities"] = capabilities
        if hostname is not None:
            values["hostname"] = hostname
        if os is not None:
            values["os"] = os
        if os_version is not None:
            values["os_version"] = os_version
        if arch is not None:
            values["arch"] = arch
        if agent_version is not None:
            values["agent_version"] = agent_version
        if connection_id is not None:
            values["connection_id"] = connection_id
        if last_resources is not None:
            values["last_resources"] = last_resources

        insert_stmt = pg_insert(Bridge).values(**values)
        update_cols = {k: v for k, v in values.items() if k != "host_id"}
        update_cols["updated_at"] = now
        returning_stmt = insert_stmt.on_conflict_do_update(
            index_elements=["host_id"],
            set_=update_cols,
        ).returning(Bridge)

        result = await self._session.execute(returning_stmt)
        bridge = result.scalar_one()
        await logger.adebug("bridge_upserted", host_id=host_id)
        return bridge

    async def get_by_host_id(self, host_id: str) -> Bridge | None:
        """Get a bridge by host_id."""
        query = select(Bridge).where(Bridge.host_id == host_id)
        result = await self._session.execute(query)
        return result.scalar_one_or_none()

    async def list_all(self, status_filter: str | None = None) -> list[Bridge]:
        """List all bridges, optionally filtered by status."""
        query = select(Bridge)
        if status_filter is not None:
            query = query.where(Bridge.status == status_filter)
        query = query.order_by(Bridge.last_heartbeat_at.desc().nulls_last())
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def mark_offline(self, host_id: str) -> None:
        """Mark a bridge as offline."""
        stmt = (
            update(Bridge)
            .where(Bridge.host_id == host_id)
            .values(status="offline", updated_at=datetime.now(tz=UTC))
        )
        await self._session.execute(stmt)
