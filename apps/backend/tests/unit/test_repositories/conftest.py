"""Shared fixtures for repository tests — mirrors test_models/conftest.py.

Repositories are exercised against a real Postgres connection (skipped when
RAFRAF_TEST_DATABASE_URL / DATABASE_URL is unset), wrapped in a transaction
that rolls back on teardown. See ``tests/unit/test_models/conftest.py`` for
the same pattern; we duplicate it here rather than reach across sibling
packages so each test directory remains self-contained.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.bridge import Bridge


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
