"""Tests for SubagentRepository — upsert, list, update_status.

Requires a real Postgres DB. Skipped when no RAFRAF_TEST_DATABASE_URL /
DATABASE_URL is configured (see conftest.py).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bridge import Bridge
from app.repositories.subagent_repo import SubagentRepository


class TestUpsertSubagent:
    """upsert_subagent — insert path + conflict path."""

    @pytest.mark.asyncio
    async def test_insert_new_subagent_returns_row(
        self,
        db_session: AsyncSession,
        bridge_row: Bridge,
    ) -> None:
        repo = SubagentRepository(db_session)
        spawned = datetime.now(tz=UTC)

        row = await repo.upsert_subagent(
            bridge_id=bridge_row.id,
            session_id="sess-insert",
            task_id="t-100",
            spawned_at=spawned,
            name="initial",
            description="first attempt",
            prompt_preview="Do the thing",
            subagent_type="general-purpose",
            isolation="worktree",
            status="spawned",
        )

        assert row.id is not None
        assert row.bridge_id == bridge_row.id
        assert row.session_id == "sess-insert"
        assert row.task_id == "t-100"
        assert row.name == "initial"
        assert row.subagent_type == "general-purpose"
        assert row.isolation == "worktree"
        assert row.status == "spawned"
        assert row.summary is None
        assert row.completed_at is None

    @pytest.mark.asyncio
    async def test_upsert_conflict_updates_mutable_fields_only(
        self,
        db_session: AsyncSession,
        bridge_row: Bridge,
    ) -> None:
        repo = SubagentRepository(db_session)
        spawned = datetime.now(tz=UTC)

        # First insert.
        first = await repo.upsert_subagent(
            bridge_id=bridge_row.id,
            session_id="sess-conflict",
            task_id="t-200",
            spawned_at=spawned,
            status="spawned",
            prompt_preview="initial preview",
        )
        first_id = first.id
        first_spawned = first.spawned_at

        # Conflict path — different spawned_at must NOT overwrite the original
        # (immutable). Status + summary must be applied.
        completed = datetime.now(tz=UTC) + timedelta(seconds=30)
        second = await repo.upsert_subagent(
            bridge_id=bridge_row.id,
            session_id="sess-conflict",
            task_id="t-200",
            spawned_at=completed,  # ignored on conflict path
            status="completed",
            summary="Done",
            total_tokens=999,
            tool_uses=3,
            duration_ms=12345,
            completed_at=completed,
        )

        assert second.id == first_id, "upsert should return the same row, not insert a new one"
        assert second.status == "completed"
        assert second.summary == "Done"
        assert second.total_tokens == 999
        assert second.tool_uses == 3
        assert second.duration_ms == 12345
        assert second.completed_at is not None
        # spawned_at must remain the original timestamp.
        assert second.spawned_at == first_spawned
        # updated_at must have been written by the conflict-path SET clause.
        assert second.updated_at is not None


class TestListSubagentsForSession:
    """list_subagents_for_session — chronological ordering, scope to session."""

    @pytest.mark.asyncio
    async def test_returns_empty_for_unknown_session(
        self,
        db_session: AsyncSession,
    ) -> None:
        repo = SubagentRepository(db_session)
        rows = await repo.list_subagents_for_session("never-existed")
        assert rows == []

    @pytest.mark.asyncio
    async def test_returns_only_matching_session_in_spawn_order(
        self,
        db_session: AsyncSession,
        bridge_row: Bridge,
    ) -> None:
        repo = SubagentRepository(db_session)
        base = datetime.now(tz=UTC)

        # Three subagents in target session, one in a noise session.
        await repo.upsert_subagent(
            bridge_id=bridge_row.id,
            session_id="sess-list",
            task_id="t-c",
            spawned_at=base + timedelta(seconds=2),
        )
        await repo.upsert_subagent(
            bridge_id=bridge_row.id,
            session_id="sess-list",
            task_id="t-a",
            spawned_at=base,
        )
        await repo.upsert_subagent(
            bridge_id=bridge_row.id,
            session_id="sess-list",
            task_id="t-b",
            spawned_at=base + timedelta(seconds=1),
        )
        await repo.upsert_subagent(
            bridge_id=bridge_row.id,
            session_id="sess-noise",
            task_id="t-x",
            spawned_at=base,
        )

        rows = await repo.list_subagents_for_session("sess-list")
        assert [r.task_id for r in rows] == ["t-a", "t-b", "t-c"], (
            "list_subagents_for_session must order by spawned_at ASC"
        )


class TestUpdateSubagentStatus:
    """update_subagent_status — patch path + miss path."""

    @pytest.mark.asyncio
    async def test_returns_false_when_no_row_matches(
        self,
        db_session: AsyncSession,
    ) -> None:
        repo = SubagentRepository(db_session)
        result = await repo.update_subagent_status(
            session_id="ghost",
            task_id="ghost-t",
            status="completed",
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_updates_status_and_terminal_fields(
        self,
        db_session: AsyncSession,
        bridge_row: Bridge,
    ) -> None:
        repo = SubagentRepository(db_session)
        spawned = datetime.now(tz=UTC)

        await repo.upsert_subagent(
            bridge_id=bridge_row.id,
            session_id="sess-upd",
            task_id="t-upd",
            spawned_at=spawned,
            status="in_progress",
        )

        completed = spawned + timedelta(seconds=15)
        ok = await repo.update_subagent_status(
            session_id="sess-upd",
            task_id="t-upd",
            status="failed",
            summary="boom",
            total_tokens=42,
            tool_uses=1,
            duration_ms=999,
            completed_at=completed,
        )
        assert ok is True

        rows = await repo.list_subagents_for_session("sess-upd")
        assert len(rows) == 1
        row = rows[0]
        assert row.status == "failed"
        assert row.summary == "boom"
        assert row.total_tokens == 42
        assert row.tool_uses == 1
        assert row.duration_ms == 999
        assert row.completed_at is not None
        # updated_at must have been bumped.
        assert row.updated_at is not None

    @pytest.mark.asyncio
    async def test_partial_status_update_does_not_clobber_unset_fields(
        self,
        db_session: AsyncSession,
        bridge_row: Bridge,
    ) -> None:
        repo = SubagentRepository(db_session)
        spawned = datetime.now(tz=UTC)

        await repo.upsert_subagent(
            bridge_id=bridge_row.id,
            session_id="sess-partial",
            task_id="t-partial",
            spawned_at=spawned,
            status="spawned",
            summary="early summary",
            total_tokens=10,
        )

        ok = await repo.update_subagent_status(
            session_id="sess-partial",
            task_id="t-partial",
            status="in_progress",
        )
        assert ok is True

        rows = await repo.list_subagents_for_session("sess-partial")
        row = rows[0]
        assert row.status == "in_progress"
        # Existing fields stay because the patch did not include them.
        assert row.summary == "early summary"
        assert row.total_tokens == 10
