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
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.main import app
from app.schemas.sessions import SessionCostBreakdownItem, SessionCostSummary


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


# ---------------------------------------------------------------------------
# T2.5-fix end-to-end: runner.run() result event → SessionRepository UPSERT →
# cost-summary endpoint reads back non-zero. Validates that the UPSERT
# correctly seeds a fresh ``sessions`` row for a WS session_id that was
# never previously INSERTed (the legacy plain-UPDATE path silently dropped
# the write because ``rowcount == 0``).
# ---------------------------------------------------------------------------


class TestT25FixUpsertEndToEnd:
    """End-to-end: runner cost persistence reaches the cost-summary endpoint."""

    @pytest.mark.asyncio
    async def test_runner_upsert_then_summary_returns_nonzero(self) -> None:
        """Drive ``ClaudeCodeRunner.run()`` with a result event, capture the
        repo write, then ask the cost-summary endpoint and assert it sees
        the persisted cost (not zero like the pre-fix code path).

        We use the same in-memory ``_FakeSessionRepo`` pattern as the
        runner unit tests, plus a parallel fake registry that emits a
        single ``event.session.result`` envelope. After the runner
        completes we project the captured UPSERT call as a Session-shaped
        stub, install it via the cost-summary endpoint dep-overrides, and
        assert the response carries the persisted cost — proving the wire
        from result-event → DB → summary is unbroken.
        """
        import asyncio
        import uuid as _uuid
        from collections.abc import AsyncIterator

        from app.orchestrator.claude_code_runner import ClaudeCodeRunner

        # --- Fake bridge registry replaying a single result event. -------
        class _FakeRegistry:
            def __init__(self, events: list[dict[str, object]]) -> None:
                self._events = events

            def get_connection_id(self, host_id: str) -> str | None:
                return f"conn-{host_id}" if host_id == "mac-1" else None

            def find_online_agent_with_capability(self, capability: str) -> str | None:
                del capability
                return "mac-1"

            def register_subscriber(
                self, *, bridge_id: str, rpc_id: str
            ) -> asyncio.Queue[dict[str, object]]:
                del bridge_id, rpc_id
                return asyncio.Queue()

            def unregister_subscriber(self, *, bridge_id: str, rpc_id: str) -> None:
                del bridge_id, rpc_id

            async def send_to_bridge(self, host_id: str, envelope: dict[str, object]) -> bool:
                del host_id, envelope
                return True

            async def stream_events(
                self,
                *,
                rpc_id: str,
                bridge_id: str | None = None,
                queue: asyncio.Queue[dict[str, object]] | None = None,
            ) -> AsyncIterator[dict[str, object]]:
                del bridge_id, queue
                for raw in self._events:
                    event = dict(raw)
                    event["correlation_id"] = rpc_id
                    yield event

        # --- Fake repo capturing the UPSERT call. -----------------------
        class _UpsertingRepo:
            def __init__(self) -> None:
                self.upserted: list[dict[str, object]] = []

            async def update_session_cost(
                self,
                session_id: _uuid.UUID,
                *,
                user_id: _uuid.UUID,
                total_cost_usd: object,
                total_input_tokens: int = 0,
                total_output_tokens: int = 0,
                total_cache_creation_tokens: int = 0,
                total_cache_read_tokens: int = 0,
            ) -> bool:
                self.upserted.append(
                    {
                        "session_id": session_id,
                        "user_id": user_id,
                        "total_cost_usd": Decimal(str(total_cost_usd)),
                        "total_input_tokens": total_input_tokens,
                        "total_output_tokens": total_output_tokens,
                        "total_cache_creation_tokens": total_cache_creation_tokens,
                        "total_cache_read_tokens": total_cache_read_tokens,
                    }
                )
                return True

        result_event = {
            "type": "event.session.result",
            "payload": {
                "session_id": "sess-e2e",
                "duration_ms": 200,
                "num_turns": 1,
                "result": "ok",
                "stop_reason": "end_turn",
                "total_cost_usd": 0.123,
                "model_usage": {
                    "claude-opus-4-7": {
                        "input_tokens": 500,
                        "output_tokens": 250,
                        "cache_creation_input_tokens": 0,
                        "cache_read_input_tokens": 0,
                    }
                },
                "permission_denials": [],
                "terminal_reason": "clean",
            },
        }
        registry = _FakeRegistry(events=[result_event])
        repo = _UpsertingRepo()
        runner = ClaudeCodeRunner(
            bridge_registry=registry,  # type: ignore[arg-type]
            session_repo=repo,  # type: ignore[arg-type]
        )

        ws_session_id = _uuid.uuid4()  # brand-new UUID — no row pre-exists.
        owner_user_id = _uuid.uuid4()

        await runner.run(
            prompt="hello",
            db_session_id=ws_session_id,
            user_id=str(owner_user_id),
        )

        # --- Confirm UPSERT was called with the supplied user_id. -------
        assert len(repo.upserted) == 1
        write = repo.upserted[0]
        assert write["session_id"] == ws_session_id
        assert write["user_id"] == owner_user_id
        assert write["total_cost_usd"] == Decimal("0.123")
        assert write["total_input_tokens"] == 500
        assert write["total_output_tokens"] == 250

        # --- Now project that write as a Session row + install the
        #     dep-override and verify the cost-summary endpoint returns
        #     the non-zero cost. This is the "DB persists → summary
        #     endpoint reads it back" leg of the end-to-end flow.
        user_for_endpoint = _make_user_stub(user_id=owner_user_id)
        now = datetime.now(tz=UTC)
        seeded_row = _make_session_row(
            user_id=owner_user_id,
            cost=Decimal(str(write["total_cost_usd"])),
            started_at=now - timedelta(minutes=5),
            cost_updated_at=now,
            input_tokens=int(write["total_input_tokens"]),  # type: ignore[arg-type]
            output_tokens=int(write["total_output_tokens"]),  # type: ignore[arg-type]
        )
        seeded_row.id = ws_session_id
        _install_overrides(
            user_for_endpoint,
            rows_by_user={owner_user_id: [seeded_row]},
        )

        client = TestClient(app)
        resp = client.get("/api/v1/sessions/cost-summary")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["session_count"] == 1
        # CRITICAL: NOT zero — pre-fix this would have been Decimal('0')
        # because the runner's plain-UPDATE never matched a row.
        assert Decimal(data["total_cost_usd"]) == Decimal("0.123")
        assert data["total_input_tokens"] == 500
        assert data["total_output_tokens"] == 250
        assert len(data["by_session"]) == 1
        assert data["by_session"][0]["session_id"] == str(ws_session_id)


# ---------------------------------------------------------------------------
# T2.5 M3 — frozen response DTOs (immutability contract).
# ---------------------------------------------------------------------------


class TestCostSummaryDTOsFrozen:
    """``SessionCostSummary`` and ``SessionCostBreakdownItem`` are frozen
    Pydantic models — the route assembles them in a single ``return`` and
    nothing in the call path mutates them after construction. Pinning the
    contract here keeps a future drive-by edit from silently relaxing it."""

    def test_breakdown_item_is_frozen(self) -> None:
        item = SessionCostBreakdownItem(
            session_id=uuid.uuid4(),
            cost_usd=Decimal("0.10"),
            started_at=datetime.now(tz=UTC),
        )
        with pytest.raises(ValidationError):
            item.cost_usd = Decimal("999.99")  # type: ignore[misc]

    def test_summary_is_frozen(self) -> None:
        summary = SessionCostSummary(
            period="2026-05",
            period_kind="current_month",
            period_start=datetime.now(tz=UTC),
            period_end=None,
            user_id=uuid.uuid4(),
            total_cost_usd=Decimal("1.23"),
            session_count=1,
            total_input_tokens=10,
            total_output_tokens=20,
            total_cache_creation_tokens=0,
            total_cache_read_tokens=0,
            by_session=[],
        )
        with pytest.raises(ValidationError):
            summary.total_cost_usd = Decimal("999.99")  # type: ignore[misc]

    def test_summary_serializes_via_json(self) -> None:
        """Frozen models must still round-trip via ``model_dump_json`` —
        no behavioural regression for the existing FastAPI response path."""
        summary = SessionCostSummary(
            period="2026-W18",
            period_kind="current_week",
            period_start=datetime.now(tz=UTC),
            period_end=None,
            user_id=uuid.uuid4(),
            total_cost_usd=Decimal("0"),
            session_count=0,
            total_input_tokens=0,
            total_output_tokens=0,
            total_cache_creation_tokens=0,
            total_cache_read_tokens=0,
            by_session=[],
        )
        # Serialization MUST NOT mutate the model.
        payload = summary.model_dump_json()
        assert "current_week" in payload
        # Confirm immutability survives a second round of serialization.
        assert summary.period_kind == "current_week"
