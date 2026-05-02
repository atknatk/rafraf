"""Tests for the Subagent ORM model.

Covers row insert, FK CASCADE on bridge deletion, and the
``subagents_task_session_uniq`` UNIQUE constraint. Requires a real Postgres
DB (skipped via ``conftest.db_session`` fixture when DATABASE_URL /
RAFRAF_TEST_DATABASE_URL is unset).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bridge import Bridge
from app.models.subagent import Subagent


def _make_subagent(
    bridge_id: uuid.UUID,
    *,
    session_id: str = "sess-abc",
    task_id: str = "task-001",
    name: str | None = "research subagent",
    description: str | None = "Investigate the codebase for X",
    prompt_preview: str | None = "Find all references to X",
    subagent_type: str | None = "general-purpose",
    isolation: str | None = None,
    status: str = "spawned",
) -> Subagent:
    return Subagent(
        bridge_id=bridge_id,
        session_id=session_id,
        task_id=task_id,
        name=name,
        description=description,
        prompt_preview=prompt_preview,
        subagent_type=subagent_type,
        isolation=isolation,
        status=status,
        spawned_at=datetime.now(tz=UTC),
    )


class TestSubagentInsert:
    """Basic insert + read-back."""

    @pytest.mark.asyncio
    async def test_insert_minimal_row_round_trips(
        self,
        db_session: AsyncSession,
        bridge_row: Bridge,
    ) -> None:
        sub = _make_subagent(bridge_row.id)
        db_session.add(sub)
        await db_session.flush()

        row = (
            await db_session.execute(select(Subagent).where(Subagent.task_id == "task-001"))
        ).scalar_one()

        assert row.bridge_id == bridge_row.id
        assert row.session_id == "sess-abc"
        assert row.task_id == "task-001"
        assert row.subagent_type == "general-purpose"
        assert row.status == "spawned"
        assert row.id is not None
        assert row.spawned_at is not None
        assert row.created_at is not None
        # Optional fields default to None when not set
        assert row.completed_at is None
        assert row.summary is None

    @pytest.mark.asyncio
    async def test_insert_with_terminal_payload(
        self,
        db_session: AsyncSession,
        bridge_row: Bridge,
    ) -> None:
        sub = _make_subagent(bridge_row.id, status="completed")
        sub.summary = "Found 3 references"
        sub.total_tokens = 12_345
        sub.tool_uses = 7
        sub.duration_ms = 4_321
        sub.completed_at = datetime.now(tz=UTC)

        db_session.add(sub)
        await db_session.flush()

        row = (
            await db_session.execute(select(Subagent).where(Subagent.task_id == "task-001"))
        ).scalar_one()

        assert row.status == "completed"
        assert row.summary == "Found 3 references"
        assert row.total_tokens == 12_345
        assert row.tool_uses == 7
        assert row.duration_ms == 4_321
        assert row.completed_at is not None


class TestSubagentUniqueConstraint:
    """``subagents_task_session_uniq`` (session_id, task_id)."""

    @pytest.mark.asyncio
    async def test_duplicate_session_task_pair_raises_integrity_error(
        self,
        db_session: AsyncSession,
        bridge_row: Bridge,
    ) -> None:
        a = _make_subagent(bridge_row.id, session_id="sess-x", task_id="t-1")
        db_session.add(a)
        await db_session.flush()

        # Use a SAVEPOINT so the outer transaction (owned by the conftest)
        # survives the IntegrityError and can still be rolled back at
        # teardown without a SAWarning.
        sp = await db_session.begin_nested()
        b = _make_subagent(bridge_row.id, session_id="sess-x", task_id="t-1")
        db_session.add(b)
        with pytest.raises(IntegrityError):
            await db_session.flush()
        await sp.rollback()

    @pytest.mark.asyncio
    async def test_same_task_id_in_different_sessions_is_allowed(
        self,
        db_session: AsyncSession,
        bridge_row: Bridge,
    ) -> None:
        a = _make_subagent(bridge_row.id, session_id="sess-1", task_id="t-1")
        b = _make_subagent(bridge_row.id, session_id="sess-2", task_id="t-1")
        db_session.add_all([a, b])
        await db_session.flush()  # must NOT raise


class TestSubagentForeignKey:
    """``bridge_id`` FK with ON DELETE CASCADE."""

    @pytest.mark.asyncio
    async def test_delete_bridge_cascades_to_subagents(
        self,
        db_session: AsyncSession,
        bridge_row: Bridge,
    ) -> None:
        sub = _make_subagent(bridge_row.id, session_id="sess-cascade", task_id="t-c")
        db_session.add(sub)
        await db_session.flush()

        # Sanity check: row exists.
        existing = (
            await db_session.execute(select(Subagent).where(Subagent.session_id == "sess-cascade"))
        ).scalar_one_or_none()
        assert existing is not None

        # Delete the bridge — the subagent must vanish via FK CASCADE.
        await db_session.execute(delete(Bridge).where(Bridge.id == bridge_row.id))
        await db_session.flush()

        gone = (
            await db_session.execute(select(Subagent).where(Subagent.session_id == "sess-cascade"))
        ).scalar_one_or_none()
        assert gone is None


class TestSubagentRelationship:
    """``Bridge.subagents`` ORM relationship round-trip."""

    @pytest.mark.asyncio
    async def test_bridge_subagents_relationship_lists_inserts(
        self,
        db_session: AsyncSession,
        bridge_row: Bridge,
    ) -> None:
        a = _make_subagent(bridge_row.id, session_id="sess-r", task_id="t-a")
        b = _make_subagent(bridge_row.id, session_id="sess-r", task_id="t-b")
        db_session.add_all([a, b])
        await db_session.flush()

        await db_session.refresh(bridge_row, attribute_names=["subagents"])
        task_ids = sorted(s.task_id for s in bridge_row.subagents)
        assert task_ids == ["t-a", "t-b"]
