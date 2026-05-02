"""Shared fixtures for model + repository tests that need a real DB.

Tests that require DB access read ``RAFRAF_TEST_DATABASE_URL`` (preferred) or
fall back to ``DATABASE_URL`` from the environment. When neither is set the
fixture skips the dependent test so plain ``pytest -q`` keeps working in
sandboxes without Postgres.

Each test runs inside a SAVEPOINT-style transaction that is rolled back at
teardown — no test data persists across runs.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import Base, Bridge


def _resolve_test_db_url() -> str | None:
    """Return the URL to use for real-DB tests, or None if unavailable."""
    return os.environ.get("RAFRAF_TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an AsyncSession backed by a real Postgres connection.

    Skips the test when no test DB URL is configured. The session is wrapped
    in a transaction that is rolled back on teardown so tests stay
    independent.
    """
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
    """Insert a throwaway Bridge row that subagent FK tests can reference.

    The row is inserted inside the test's rollback-bound transaction so it
    vanishes on teardown.
    """
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


# Re-export so the test files can mention it by name.
__all__ = ["db_session", "bridge_row", "Base"]
