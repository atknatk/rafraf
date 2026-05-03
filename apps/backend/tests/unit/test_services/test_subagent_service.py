"""Unit tests for SubagentService — REST hydration of persisted subagents.

Owned by V1.x Item 9. Pins three contracts:

1. ``list_for_session`` returns only rows whose ``session_id`` matches
   the requested claude session (no leak across sibling sessions).
2. An unknown session id resolves to an empty list (no exception, no 404
   — there is no FK to ``sessions`` so we cannot meaningfully 404).
3. Returned rows are ordered chronologically (``spawned_at ASC``),
   matching the iOS timeline rendering order.

These tests use the real ``SubagentRepository`` against a real Postgres
connection (skipped when ``RAFRAF_TEST_DATABASE_URL`` / ``DATABASE_URL``
is unset). Coverage of the repo's pure SQL is already in
``test_subagent_repo.py``; here we only assert the service-layer
projection.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.bridge import Bridge
from app.repositories.subagent_repo import SubagentRepository
from app.services.subagent_service import SubagentService

# ---------------------------------------------------------------------------
# Fixtures (mirror tests/unit/test_repositories/conftest.py — duplicated so
# each directory remains self-contained per the existing repo convention).
# ---------------------------------------------------------------------------


def _resolve_test_db_url() -> str | None:
    return os.environ.get("RAFRAF_TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    db_url = _resolve_test_db_url()
    if not db_url:
        pytest.skip(
            "Real DB tests need RAFRAF_TEST_DATABASE_URL or DATABASE_URL "
            "to point at an asyncpg-compatible Postgres instance."
        )

    engine = create_async_engine(db_url, echo=False, pool_pre_ping=True)
    session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with engine.connect() as connection:
        trans = await connection.begin()
        async with session_factory(bind=connection) as session:
            try:
                yield session
            finally:
                await trans.rollback()

    await engine.dispose()


@pytest_asyncio.fixture
async def bridge_row(db_session: AsyncSession) -> Bridge:
    bridge = Bridge(
        id=uuid.uuid4(),
        host_id=f"test-bridge-{uuid.uuid4().hex[:8]}",
        hostname="test-host",
        os="darwin",
        capabilities=["docker"],
        status="online",
    )
    db_session.add(bridge)
    await db_session.flush()
    return bridge


# ---------------------------------------------------------------------------
# SubagentService.list_for_session
# ---------------------------------------------------------------------------


class TestListForSession:
    """SubagentService.list_for_session contract."""

    @pytest.mark.asyncio
    async def test_list_for_session_returns_only_session_subagents(
        self,
        db_session: AsyncSession,
        bridge_row: Bridge,
    ) -> None:
        """3 subagents in session A + 2 in session B → only A's are returned."""
        repo = SubagentRepository(db_session)
        base = datetime.now(tz=UTC)

        # Session A — 3 subagents.
        for offset, task_id in enumerate(["a1", "a2", "a3"]):
            await repo.upsert_subagent(
                bridge_id=bridge_row.id,
                session_id="sess-A",
                task_id=task_id,
                spawned_at=base + timedelta(seconds=offset),
                description=f"task {task_id}",
                status="spawned",
            )

        # Session B — 2 subagents (must NOT appear in the A query).
        for offset, task_id in enumerate(["b1", "b2"]):
            await repo.upsert_subagent(
                bridge_id=bridge_row.id,
                session_id="sess-B",
                task_id=task_id,
                spawned_at=base + timedelta(seconds=offset),
                status="spawned",
            )

        svc = SubagentService(db_session)
        rows = await svc.list_for_session("sess-A")

        assert len(rows) == 3
        assert {r.session_id for r in rows} == {"sess-A"}
        # ``r.id`` is the bridge task_id (post-reviewer contract — see
        # SubagentResponse docstring; the SQL UUID lives on ``r.db_id``).
        assert {r.id for r in rows} == {"a1", "a2", "a3"}
        # Each row must carry the description we wrote.
        for row in rows:
            assert row.description is not None
            assert row.description.startswith("task ")

    @pytest.mark.asyncio
    async def test_list_for_session_empty_when_no_subagents(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Unknown session_id → empty list (no exception, no 404)."""
        svc = SubagentService(db_session)
        rows = await svc.list_for_session("never-existed")
        assert rows == []

    @pytest.mark.asyncio
    async def test_list_for_session_orders_by_started_at(
        self,
        db_session: AsyncSession,
        bridge_row: Bridge,
    ) -> None:
        """Returned order MUST be chronological (spawned_at ASC)."""
        repo = SubagentRepository(db_session)
        base = datetime.now(tz=UTC)

        # Insert deliberately out of order to prove the ORDER BY.
        await repo.upsert_subagent(
            bridge_id=bridge_row.id,
            session_id="sess-order",
            task_id="late",
            spawned_at=base + timedelta(seconds=10),
        )
        await repo.upsert_subagent(
            bridge_id=bridge_row.id,
            session_id="sess-order",
            task_id="early",
            spawned_at=base,
        )
        await repo.upsert_subagent(
            bridge_id=bridge_row.id,
            session_id="sess-order",
            task_id="middle",
            spawned_at=base + timedelta(seconds=5),
        )

        svc = SubagentService(db_session)
        rows = await svc.list_for_session("sess-order")

        # ``r.id`` is the bridge task_id (not the SQL UUID) per the post-
        # reviewer contract — see SubagentResponse docstring.
        assert [r.id for r in rows] == ["early", "middle", "late"], (
            "list_for_session must return rows ordered by started_at ASC"
        )

    @pytest.mark.asyncio
    async def test_list_for_session_dto_shape(
        self,
        db_session: AsyncSession,
        bridge_row: Bridge,
    ) -> None:
        """DTO carries the fields iOS needs (id, status, started_at, etc.).

        Post-reviewer contract:
        - ``id`` is the bridge task_id (string), NOT the SQL UUID.
        - SQL primary key surfaces on ``db_id``.
        - Terminal summary lives on ``summary`` (NOT ``output_summary``).
        """
        repo = SubagentRepository(db_session)
        spawned = datetime.now(tz=UTC)
        completed = spawned + timedelta(seconds=30)

        await repo.upsert_subagent(
            bridge_id=bridge_row.id,
            session_id="sess-shape",
            task_id="t-shape",
            spawned_at=spawned,
            parent_session_id="parent-sess",
            name="developer",
            description="run the linter",
            prompt_preview="please run the linter",
            subagent_type="general-purpose",
            isolation="worktree",
            status="completed",
            summary="all green",
            total_tokens=42,
            tool_uses=3,
            duration_ms=15000,
            completed_at=completed,
        )

        svc = SubagentService(db_session)
        rows = await svc.list_for_session("sess-shape")
        assert len(rows) == 1
        row = rows[0]

        # Identity contract.
        assert row.id == "t-shape"  # bridge task_id, NOT SQL UUID
        assert isinstance(row.db_id, uuid.UUID)

        # Ownership.
        assert row.parent_id == "parent-sess"
        assert row.session_id == "sess-shape"

        # Lifecycle + descriptive metadata.
        assert row.status == "completed"
        assert row.name == "developer"
        assert row.description == "run the linter"
        assert row.prompt_preview == "please run the linter"
        assert row.subagent_type == "general-purpose"
        assert row.isolation == "worktree"

        # Terminal payload — JSON key is ``summary`` (NOT ``output_summary``).
        assert row.summary == "all green"
        assert row.total_tokens == 42
        assert row.tool_uses == 3
        assert row.duration_ms == 15000

        # Live-only fields not persisted today.
        assert row.activity is None
        assert row.progress_percent is None

        # Timestamps.
        assert row.started_at == spawned
        assert row.completed_at is not None

    @pytest.mark.asyncio
    async def test_list_for_session_passes_through_name_and_description(
        self,
        db_session: AsyncSession,
        bridge_row: Bridge,
    ) -> None:
        """``name`` and ``description`` are surfaced verbatim — no server-side fallback.

        Reviewer feedback (Important #1): iOS already does the fallback in
        its mapper (``dto.name ?? dto.subagentType ?? "subagent"``). The
        backend MUST keep them as separate fields so iOS retains the
        ability to distinguish a short spawn-time label from a long
        description; collapsing them here would lose information.
        """
        repo = SubagentRepository(db_session)
        # Case 1: only name (description NULL) — iOS will fall back to name.
        await repo.upsert_subagent(
            bridge_id=bridge_row.id,
            session_id="sess-name-only",
            task_id="t-name",
            spawned_at=datetime.now(tz=UTC),
            name="short label",
            # No description supplied.
        )

        svc = SubagentService(db_session)
        rows = await svc.list_for_session("sess-name-only")
        assert len(rows) == 1
        # Server passes both through verbatim. iOS handles the fallback.
        assert rows[0].name == "short label"
        assert rows[0].description is None
