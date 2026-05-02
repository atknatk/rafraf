"""Tests for SessionRepository — T2.5 cost tracking.

Covers ``update_session_cost`` (cumulative ADD) plus the
``list_costs_for_user_in_period`` aggregation helper. Uses the same
real-DB conftest as ``test_subagent_repo.py``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session import Session
from app.models.user import User
from app.repositories.session_repo import (
    SessionRepository,
    resolve_period_window,
)
from app.repositories.user_repository import UserRepository


async def _make_user(db_session: AsyncSession) -> User:
    """Spin up a fresh user row for tests that need one."""
    repo = UserRepository(db_session)
    user = await repo.create(
        email=f"cost-{uuid.uuid4().hex[:8]}@test.local",
        hashed_password="x" * 60,
    )
    await db_session.flush()
    return user


class TestUpdateSessionCost:
    """update_session_cost — cumulative ADD via COALESCE semantics."""

    @pytest.mark.asyncio
    async def test_returns_false_for_unknown_session(
        self, db_session: AsyncSession
    ) -> None:
        repo = SessionRepository(db_session)
        ok = await repo.update_session_cost(
            uuid.uuid4(),
            total_cost_usd=Decimal("0.01"),
        )
        assert ok is False

    @pytest.mark.asyncio
    async def test_first_increment_initialises_columns(
        self, db_session: AsyncSession
    ) -> None:
        user = await _make_user(db_session)
        repo = SessionRepository(db_session)
        record = await repo.create(user_id=user.id)

        ok = await repo.update_session_cost(
            record.id,
            total_cost_usd=Decimal("0.123456"),
            total_input_tokens=10,
            total_output_tokens=20,
            total_cache_creation_tokens=3,
            total_cache_read_tokens=5,
        )
        assert ok is True

        await db_session.refresh(record)
        assert record.total_cost_usd == Decimal("0.123456")
        assert record.total_input_tokens == 10
        assert record.total_output_tokens == 20
        assert record.total_cache_creation_tokens == 3
        assert record.total_cache_read_tokens == 5
        assert record.cost_updated_at is not None

    @pytest.mark.asyncio
    async def test_second_increment_adds_cumulatively(
        self, db_session: AsyncSession
    ) -> None:
        user = await _make_user(db_session)
        repo = SessionRepository(db_session)
        record = await repo.create(user_id=user.id)

        await repo.update_session_cost(
            record.id,
            total_cost_usd=Decimal("0.10"),
            total_input_tokens=5,
            total_output_tokens=7,
            total_cache_creation_tokens=1,
            total_cache_read_tokens=2,
        )
        await repo.update_session_cost(
            record.id,
            total_cost_usd=Decimal("0.05"),
            total_input_tokens=3,
            total_output_tokens=4,
            total_cache_creation_tokens=0,
            total_cache_read_tokens=8,
        )

        await db_session.refresh(record)
        # Cumulative ADD across two increments.
        assert record.total_cost_usd == Decimal("0.150000")
        assert record.total_input_tokens == 8
        assert record.total_output_tokens == 11
        assert record.total_cache_creation_tokens == 1
        assert record.total_cache_read_tokens == 10

    @pytest.mark.asyncio
    async def test_negative_cost_clamped_to_zero(
        self, db_session: AsyncSession
    ) -> None:
        user = await _make_user(db_session)
        repo = SessionRepository(db_session)
        record = await repo.create(user_id=user.id)

        await repo.update_session_cost(
            record.id,
            total_cost_usd=Decimal("-0.50"),
        )
        await db_session.refresh(record)
        # Default 0 + clamped 0 == 0.
        assert record.total_cost_usd == Decimal("0.000000")


class TestListCostsForUserInPeriod:
    """list_costs_for_user_in_period — window filter + ordering."""

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_sessions_in_window(
        self, db_session: AsyncSession
    ) -> None:
        user = await _make_user(db_session)
        repo = SessionRepository(db_session)
        rows = await repo.list_costs_for_user_in_period(
            user_id=user.id,
            period_start=datetime.now(tz=UTC),
        )
        assert rows == []

    @pytest.mark.asyncio
    async def test_filters_outside_window_and_orders_desc(
        self, db_session: AsyncSession
    ) -> None:
        user = await _make_user(db_session)
        repo = SessionRepository(db_session)

        old_session = await repo.create(user_id=user.id)
        recent_session = await repo.create(user_id=user.id)
        await repo.update_session_cost(
            old_session.id, total_cost_usd=Decimal("0.01")
        )
        await repo.update_session_cost(
            recent_session.id, total_cost_usd=Decimal("0.02")
        )
        # Manually backdate the older session to outside the window.
        await db_session.refresh(old_session)
        old_session.cost_updated_at = datetime.now(tz=UTC) - timedelta(days=60)
        await db_session.flush()

        # Window: last 30 days.
        rows = await repo.list_costs_for_user_in_period(
            user_id=user.id,
            period_start=datetime.now(tz=UTC) - timedelta(days=30),
        )
        assert len(rows) == 1
        assert rows[0].id == recent_session.id

    @pytest.mark.asyncio
    async def test_does_not_leak_other_users(
        self, db_session: AsyncSession
    ) -> None:
        user_a = await _make_user(db_session)
        user_b = await _make_user(db_session)
        repo = SessionRepository(db_session)

        sess_b = await repo.create(user_id=user_b.id)
        await repo.update_session_cost(
            sess_b.id, total_cost_usd=Decimal("0.99")
        )

        rows = await repo.list_costs_for_user_in_period(
            user_id=user_a.id,
            period_start=datetime.now(tz=UTC) - timedelta(days=7),
        )
        assert rows == []


class TestResolvePeriodWindow:
    """Pure-function tests for the period→window mapper.

    Doesn't touch the DB — verifies the boundary arithmetic for the four
    period labels exposed by the cost-summary endpoint.
    """

    def test_current_month_starts_on_first(self) -> None:
        anchor = datetime(2026, 5, 15, 12, 30, tzinfo=UTC)
        start, end, label = resolve_period_window("current_month", now=anchor)
        assert start == datetime(2026, 5, 1, tzinfo=UTC)
        assert end is None
        assert label == "2026-05"

    def test_last_month_clamps_to_previous_month(self) -> None:
        anchor = datetime(2026, 5, 15, 12, 30, tzinfo=UTC)
        start, end, label = resolve_period_window("last_month", now=anchor)
        assert start == datetime(2026, 4, 1, tzinfo=UTC)
        assert end == datetime(2026, 5, 1, tzinfo=UTC)
        assert label == "2026-04"

    def test_last_month_year_rollover(self) -> None:
        anchor = datetime(2026, 1, 5, tzinfo=UTC)
        start, end, _ = resolve_period_window("last_month", now=anchor)
        assert start == datetime(2025, 12, 1, tzinfo=UTC)
        assert end == datetime(2026, 1, 1, tzinfo=UTC)

    def test_current_week_starts_on_monday(self) -> None:
        # 2026-05-02 is a Saturday → Monday of that ISO week is 2026-04-27.
        anchor = datetime(2026, 5, 2, 9, 0, tzinfo=UTC)
        start, end, label = resolve_period_window("current_week", now=anchor)
        assert start == datetime(2026, 4, 27, tzinfo=UTC)
        assert end is None
        assert label.startswith("2026-W")

    def test_last_7_days_window(self) -> None:
        anchor = datetime(2026, 5, 2, 12, 0, tzinfo=UTC)
        start, end, label = resolve_period_window("last_7_days", now=anchor)
        assert start == anchor - timedelta(days=7)
        assert end is None
        assert label == "last_7_days"


class TestEndSessionStillWorks:
    """Sanity check: pre-T2.5 methods are not broken by the new columns."""

    @pytest.mark.asyncio
    async def test_end_session_marks_ended_at(
        self, db_session: AsyncSession
    ) -> None:
        user = await _make_user(db_session)
        repo = SessionRepository(db_session)
        record = await repo.create(user_id=user.id)
        await repo.end_session(record.id)
        # Force a fresh fetch (refresh works against the same row).
        from sqlalchemy import select

        result = await db_session.execute(
            select(Session).where(Session.id == record.id)
        )
        fetched = result.scalar_one()
        assert fetched.ended_at is not None
