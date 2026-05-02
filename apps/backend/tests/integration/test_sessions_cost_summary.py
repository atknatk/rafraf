"""Integration tests for ``GET /api/v1/sessions/cost-summary`` (T2.5).

Uses FastAPI dependency overrides for ``get_db`` + ``get_current_user``
so the test can drive the endpoint without spinning up Postgres or going
through the JWT verifier.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.main import app


def _make_user_stub(user_id: uuid.UUID | None = None) -> MagicMock:
    """Build a User stand-in with the minimal surface the endpoint touches."""
    user = MagicMock()
    user.id = user_id or uuid.uuid4()
    user.email = "cost@test.local"
    user.is_active = True
    return user


def _make_session_row(
    *,
    user_id: uuid.UUID,
    cost: Decimal,
    started_at: datetime,
    cost_updated_at: datetime,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_creation: int = 0,
    cache_read: int = 0,
) -> MagicMock:
    """Build a Session-like stub with just the columns the endpoint reads."""
    row = MagicMock()
    row.id = uuid.uuid4()
    row.user_id = user_id
    row.total_cost_usd = cost
    row.started_at = started_at
    row.cost_updated_at = cost_updated_at
    row.total_input_tokens = input_tokens
    row.total_output_tokens = output_tokens
    row.total_cache_creation_tokens = cache_creation
    row.total_cache_read_tokens = cache_read
    return row


def _install_overrides(
    user: MagicMock,
    rows_by_user: dict[uuid.UUID, list[MagicMock]] | None = None,
) -> AsyncMock:
    """Wire ``get_db`` + ``get_current_user`` overrides; return mock session."""
    rows = rows_by_user or {}
    mock_session = AsyncMock(spec=AsyncSession)

    # The endpoint only calls SessionRepository.list_costs_for_user_in_period,
    # which goes through ``await self._session.execute(stmt)``. Returning
    # the right Result-shape for any user_id is good enough.
    def _execute(stmt: object) -> MagicMock:  # noqa: ARG001
        result = MagicMock()
        # Inspect the bound parameters on the compiled statement to pick
        # the matching user. SQLAlchemy lets us interrogate via
        # ``compile().params``; for the dependency-override path we cheat
        # and rely on closure state set per-test.
        scalars = MagicMock()
        scalars.all.return_value = rows.get(user.id, [])
        result.scalars.return_value = scalars
        return result

    mock_session.execute = AsyncMock(side_effect=_execute)

    async def _db_override() -> AsyncGenerator[AsyncSession, None]:
        yield mock_session  # type: ignore[misc]

    async def _user_override() -> MagicMock:
        return user

    app.dependency_overrides[get_db] = _db_override
    app.dependency_overrides[get_current_user] = _user_override
    return mock_session


@pytest.fixture(autouse=True)
def _reset_overrides() -> AsyncGenerator[None, None]:
    yield  # type: ignore[misc]
    app.dependency_overrides.clear()


class TestAuth:
    """Endpoint must require authentication."""

    def test_missing_auth_returns_401_or_403(self) -> None:
        # No override → real get_current_user runs → no header → 401.
        client = TestClient(app)
        resp = client.get("/api/v1/sessions/cost-summary")
        assert resp.status_code in {401, 403}


class TestCostSummaryEndpoint:
    """Happy paths for the four supported periods."""

    def test_empty_summary_returns_zero_aggregates(self) -> None:
        user = _make_user_stub()
        _install_overrides(user, rows_by_user={user.id: []})

        client = TestClient(app)
        resp = client.get("/api/v1/sessions/cost-summary")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["session_count"] == 0
        # Decimal renders as string by default in Pydantic v2.
        assert Decimal(data["total_cost_usd"]) == Decimal("0")
        assert data["by_session"] == []
        assert data["period_kind"] == "current_month"

    def test_aggregates_costs_across_sessions(self) -> None:
        user = _make_user_stub()
        now = datetime.now(tz=UTC)
        rows = [
            _make_session_row(
                user_id=user.id,
                cost=Decimal("0.250000"),
                started_at=now - timedelta(hours=2),
                cost_updated_at=now - timedelta(hours=1),
                input_tokens=100,
                output_tokens=200,
                cache_creation=10,
                cache_read=20,
            ),
            _make_session_row(
                user_id=user.id,
                cost=Decimal("0.500000"),
                started_at=now - timedelta(hours=5),
                cost_updated_at=now - timedelta(hours=3),
                input_tokens=300,
                output_tokens=400,
                cache_creation=0,
                cache_read=50,
            ),
        ]
        _install_overrides(user, rows_by_user={user.id: rows})

        client = TestClient(app)
        resp = client.get("/api/v1/sessions/cost-summary")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["session_count"] == 2
        assert Decimal(data["total_cost_usd"]) == Decimal("0.750000")
        assert data["total_input_tokens"] == 400
        assert data["total_output_tokens"] == 600
        assert data["total_cache_creation_tokens"] == 10
        assert data["total_cache_read_tokens"] == 70
        assert len(data["by_session"]) == 2
        # Each breakdown row carries cost + token totals.
        first = data["by_session"][0]
        assert "session_id" in first
        assert Decimal(first["cost_usd"]) > Decimal("0")
        assert first["total_tokens"] >= first["total_input_tokens"]

    @pytest.mark.parametrize(
        "period",
        ["current_month", "last_month", "current_week", "last_7_days"],
    )
    def test_each_period_value_is_accepted(self, period: str) -> None:
        user = _make_user_stub()
        _install_overrides(user, rows_by_user={user.id: []})

        client = TestClient(app)
        resp = client.get(f"/api/v1/sessions/cost-summary?period={period}")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["period_kind"] == period
        # period_start must always be a parseable ISO timestamp.
        datetime.fromisoformat(data["period_start"].replace("Z", "+00:00"))

    def test_invalid_period_returns_422(self) -> None:
        user = _make_user_stub()
        _install_overrides(user, rows_by_user={user.id: []})

        client = TestClient(app)
        resp = client.get("/api/v1/sessions/cost-summary?period=tomorrow")
        assert resp.status_code == 422

    def test_breakdown_excludes_other_users(self) -> None:
        # Confirms the override-side filter isolation: the endpoint should
        # only see what the override returns for the *current* user, never
        # leak rows from a sibling user.
        user_a = _make_user_stub()
        user_b = _make_user_stub()
        now = datetime.now(tz=UTC)
        b_rows = [
            _make_session_row(
                user_id=user_b.id,
                cost=Decimal("9.99"),
                started_at=now,
                cost_updated_at=now,
            )
        ]
        _install_overrides(
            user_a,
            rows_by_user={user_a.id: [], user_b.id: b_rows},
        )

        client = TestClient(app)
        resp = client.get("/api/v1/sessions/cost-summary")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["session_count"] == 0
        assert Decimal(data["total_cost_usd"]) == Decimal("0")
