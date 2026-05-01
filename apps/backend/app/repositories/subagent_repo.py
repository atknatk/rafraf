"""Subagent repository — async database access layer for the subagents table.

T1.10 scope: persistence layer for the bridge's in-memory ``SubagentState``.
The wiring (claude_code_runner.py subscribes to bridge events and calls
``upsert_subagent``) is **T1.1's scope** — this module only owns the DB
access primitives.
"""

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.subagent import Subagent

logger: structlog.stdlib.BoundLogger = structlog.get_logger()


class SubagentRepository:
    """DB access layer for the ``subagents`` table.

    All methods are coroutines and operate on an injected ``AsyncSession``.
    Caller is responsible for ``commit()``/``rollback()`` — repositories
    deliberately do not own transactional boundaries (matches the existing
    ``HostAgentRepository`` / ``ProjectRepository`` pattern).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_subagent(
        self,
        *,
        bridge_id: uuid.UUID,
        session_id: str,
        task_id: str,
        spawned_at: datetime,
        parent_session_id: str | None = None,
        name: str | None = None,
        description: str | None = None,
        prompt_preview: str | None = None,
        subagent_type: str | None = None,
        isolation: str | None = None,
        status: str = "spawned",
        summary: str | None = None,
        total_tokens: int | None = None,
        tool_uses: int | None = None,
        duration_ms: int | None = None,
        completed_at: datetime | None = None,
    ) -> Subagent:
        """Insert a subagent or update the existing row keyed by (session_id, task_id).

        Conflict target is the ``subagents_task_session_uniq`` UNIQUE
        constraint. ``bridge_id`` and ``spawned_at`` are set on insert;
        subsequent upserts (e.g. from a task_notification arriving after the
        task_started row was already persisted) preserve the original
        ``spawned_at`` and update everything else.
        """
        now = datetime.now(tz=UTC)
        insert_values: dict[str, object] = {
            "bridge_id": bridge_id,
            "session_id": session_id,
            "task_id": task_id,
            "spawned_at": spawned_at,
            "status": status,
        }
        if parent_session_id is not None:
            insert_values["parent_session_id"] = parent_session_id
        if name is not None:
            insert_values["name"] = name
        if description is not None:
            insert_values["description"] = description
        if prompt_preview is not None:
            insert_values["prompt_preview"] = prompt_preview
        if subagent_type is not None:
            insert_values["subagent_type"] = subagent_type
        if isolation is not None:
            insert_values["isolation"] = isolation
        if summary is not None:
            insert_values["summary"] = summary
        if total_tokens is not None:
            insert_values["total_tokens"] = total_tokens
        if tool_uses is not None:
            insert_values["tool_uses"] = tool_uses
        if duration_ms is not None:
            insert_values["duration_ms"] = duration_ms
        if completed_at is not None:
            insert_values["completed_at"] = completed_at

        # Build the SET clause for the conflict path. We deliberately drop
        # ``bridge_id``, ``session_id``, ``task_id``, and ``spawned_at`` so a
        # late-arriving task_notification cannot rewrite the bridge ownership
        # or the original spawn timestamp. ``updated_at`` always advances.
        immutable = {"bridge_id", "session_id", "task_id", "spawned_at"}
        update_cols: dict[str, object] = {
            k: v for k, v in insert_values.items() if k not in immutable
        }
        update_cols["updated_at"] = now

        stmt = pg_insert(Subagent).values(**insert_values)
        returning_stmt = stmt.on_conflict_do_update(
            constraint="subagents_task_session_uniq",
            set_=update_cols,
        ).returning(Subagent)

        # ``populate_existing`` forces SQLAlchemy to overwrite the identity-map
        # cached attributes for any pre-existing instance with the values
        # actually returned by the RETURNING clause. Without it the conflict
        # path returns the row's pre-update snapshot.
        result = await self._session.execute(
            returning_stmt,
            execution_options={"populate_existing": True},
        )
        row = result.scalar_one()
        await logger.adebug(
            "subagent_upserted",
            session_id=session_id,
            task_id=task_id,
            status=status,
        )
        return row

    async def list_subagents_for_session(self, session_id: str) -> list[Subagent]:
        """Return every subagent recorded for a given claude session.

        Ordered by ``spawned_at ASC`` so callers get deterministic chronology.
        """
        query = (
            select(Subagent)
            .where(Subagent.session_id == session_id)
            .order_by(Subagent.spawned_at.asc())
        )
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def update_subagent_status(
        self,
        session_id: str,
        task_id: str,
        status: str,
        *,
        summary: str | None = None,
        total_tokens: int | None = None,
        tool_uses: int | None = None,
        duration_ms: int | None = None,
        completed_at: datetime | None = None,
    ) -> bool:
        """Patch an existing subagent row's status + optional terminal fields.

        Returns True if a row was matched and updated, False otherwise. Does
        **not** insert a placeholder row when the (session_id, task_id) tuple
        is unknown — that path goes through ``upsert_subagent`` so the caller
        can supply ``bridge_id`` and ``spawned_at`` for a clean insert.
        """
        now = datetime.now(tz=UTC)
        values: dict[str, object] = {
            "status": status,
            "updated_at": now,
        }
        if summary is not None:
            values["summary"] = summary
        if total_tokens is not None:
            values["total_tokens"] = total_tokens
        if tool_uses is not None:
            values["tool_uses"] = tool_uses
        if duration_ms is not None:
            values["duration_ms"] = duration_ms
        if completed_at is not None:
            values["completed_at"] = completed_at

        stmt = (
            update(Subagent)
            .where(Subagent.session_id == session_id, Subagent.task_id == task_id)
            .values(**values)
        )
        result = await self._session.execute(stmt)
        return result.rowcount > 0  # type: ignore[attr-defined, no-any-return]
