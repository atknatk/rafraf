"""Integration tests for ``GET /api/v1/sessions/{session_id}/subagents``.

V1.x Item 9 — REST hydration endpoint for the iOS
``SubagentRepositoryImpl``. Uses FastAPI dependency overrides for
``get_db`` + ``get_current_user`` and patches
``SubagentRepository.list_subagents_for_session`` directly (cleaner than
parsing compiled SQL — see reviewer NIT). No Postgres or JWT verifier
required.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models.subagent import Subagent
from app.schemas.subagents import SubagentResponse


def _make_user_stub(user_id: uuid.UUID | None = None) -> MagicMock:
    """Build a User stand-in with the minimal surface the endpoint touches."""
    user = MagicMock()
    user.id = user_id or uuid.uuid4()
    user.email = "subagents@test.local"
    user.is_active = True
    return user


def _make_subagent_row(
    *,
    session_id: str,
    task_id: str,
    spawned_at: datetime,
    bridge_id: uuid.UUID | None = None,
    status: str = "spawned",
    name: str | None = None,
    description: str | None = None,
    prompt_preview: str | None = None,
    subagent_type: str | None = None,
    isolation: str | None = None,
    summary: str | None = None,
    parent_session_id: str | None = None,
    total_tokens: int | None = None,
    tool_uses: int | None = None,
    duration_ms: int | None = None,
    updated_at: datetime | None = None,
    completed_at: datetime | None = None,
    row_id: uuid.UUID | None = None,
) -> MagicMock:
    """Build a Subagent-like stub matching the columns the service reads."""
    row = MagicMock(spec=Subagent)
    row.id = row_id or uuid.uuid4()
    row.bridge_id = bridge_id or uuid.uuid4()
    row.session_id = session_id
    row.task_id = task_id
    row.parent_session_id = parent_session_id
    row.name = name
    row.description = description
    row.prompt_preview = prompt_preview
    row.subagent_type = subagent_type
    row.isolation = isolation
    row.status = status
    row.summary = summary
    row.total_tokens = total_tokens
    row.tool_uses = tool_uses
    row.duration_ms = duration_ms
    row.spawned_at = spawned_at
    row.updated_at = updated_at
    row.completed_at = completed_at
    return row


def _install_overrides(user: MagicMock | None) -> AsyncMock:
    """Wire ``get_db`` + ``get_current_user`` overrides; return mock session.

    The mock session is a black box — the service goes through
    ``SubagentRepository.list_subagents_for_session``, which we patch in
    the test body via ``unittest.mock.patch`` on the repo method. That
    avoids brittle SQL-string parsing of the compiled statement.
    """
    mock_session = AsyncMock(spec=AsyncSession)

    async def _db_override() -> AsyncGenerator[AsyncSession, None]:
        yield mock_session  # type: ignore[misc]

    async def _user_override() -> MagicMock:
        if user is None:
            raise RuntimeError("unauthorised override should not be invoked")
        return user

    app.dependency_overrides[get_db] = _db_override
    if user is not None:
        app.dependency_overrides[get_current_user] = _user_override
    return mock_session


def _patch_repo_listing(rows_by_session: dict[str, list[MagicMock]]) -> Any:
    """Return a context-manager patch for the repo's list method.

    Routes the call by session_id so a single test can stub multiple
    sibling sessions and confirm the route never leaks across them.
    """

    async def _list_for_session(self: object, session_id: str) -> list[MagicMock]:
        del self
        return rows_by_session.get(session_id, [])

    return patch.object(
        target=__import__(
            "app.repositories.subagent_repo", fromlist=["SubagentRepository"]
        ).SubagentRepository,
        attribute="list_subagents_for_session",
        new=_list_for_session,
    )


@pytest.fixture(autouse=True)
def _reset_overrides() -> AsyncGenerator[None, None]:
    yield  # type: ignore[misc]
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Auth gate
# ---------------------------------------------------------------------------


class TestAuth:
    """Endpoint must require authentication."""

    def test_get_subagents_unauthorized_401(self) -> None:
        """No JWT → 401 (or 403 if the framework masks it)."""
        # No override for get_current_user → real dep runs → no header → 401.
        client = TestClient(app)
        resp = client.get("/api/v1/sessions/sess-foo/subagents")
        assert resp.status_code in {401, 403}


# ---------------------------------------------------------------------------
# Happy path + edge cases
# ---------------------------------------------------------------------------


class TestListSessionSubagents:
    """Happy paths for the subagents hydration endpoint."""

    def test_get_subagents_returns_session_subagents(self) -> None:
        """Happy path — known session returns its subagents."""
        user = _make_user_stub()
        base = datetime.now(tz=UTC)
        rows = [
            _make_subagent_row(
                session_id="sess-happy",
                task_id="t-1",
                spawned_at=base,
                description="lint the repo",
                name="developer",
                status="spawned",
            ),
            _make_subagent_row(
                session_id="sess-happy",
                task_id="t-2",
                spawned_at=base + timedelta(seconds=5),
                description="run tests",
                status="completed",
                summary="all green",
                total_tokens=12345,
                tool_uses=7,
                duration_ms=42_000,
                completed_at=base + timedelta(seconds=30),
            ),
        ]
        _install_overrides(user)

        client = TestClient(app)
        with _patch_repo_listing({"sess-happy": rows}):
            resp = client.get("/api/v1/sessions/sess-happy/subagents")
        assert resp.status_code == 200, resp.text

        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 2

        # Validate the response shape via the Pydantic schema — guards
        # against silent contract drift on the iOS contract.
        for item in data:
            SubagentResponse.model_validate(item)

        # Field-level smoke checks on the second (completed) row.
        completed = data[1]
        # CRITICAL contract: ``id`` is the bridge task_id (string), NOT UUID.
        assert completed["id"] == "t-2"
        assert completed["status"] == "completed"
        assert completed["description"] == "run tests"
        # JSON key is ``summary`` (not ``output_summary``) so iOS decodes it.
        assert completed["summary"] == "all green"
        assert "output_summary" not in completed
        assert completed["completed_at"] is not None
        # Terminal accounting fields surfaced.
        assert completed["total_tokens"] == 12345
        assert completed["tool_uses"] == 7
        assert completed["duration_ms"] == 42_000
        # The SQL primary key is exposed on a separate ``db_id`` field.
        assert "db_id" in completed
        uuid.UUID(completed["db_id"])  # parses cleanly

    def test_get_subagents_id_is_task_id_not_sql_uuid(self) -> None:
        """Reviewer-flagged contract bug: ``id`` MUST be the bridge task_id.

        iOS keys its in-memory cache by ``Subagent.id``. The WS push mapper
        feeds it from ``content.task_id``. If REST sent the SQL UUID, the
        same logical row would be cached under two keys → duplicate
        timeline entries on the next live update.
        """
        user = _make_user_stub()
        sql_pk = uuid.uuid4()
        bridge_task_id = "task-canonical-42"

        rows = [
            _make_subagent_row(
                session_id="sess-id-check",
                task_id=bridge_task_id,
                spawned_at=datetime.now(tz=UTC),
                row_id=sql_pk,
            ),
        ]
        _install_overrides(user)

        client = TestClient(app)
        with _patch_repo_listing({"sess-id-check": rows}):
            resp = client.get("/api/v1/sessions/sess-id-check/subagents")
        assert resp.status_code == 200, resp.text

        item = resp.json()[0]
        assert item["id"] == bridge_task_id, (
            "id MUST carry bridge task_id (iOS cache key), not the SQL UUID"
        )
        assert item["db_id"] == str(sql_pk)
        # Defensive: id must NOT parse as UUID (it's a free-form bridge token).
        with pytest.raises(ValueError, match="badly formed hexadecimal UUID string"):
            uuid.UUID(item["id"])

    def test_get_subagents_exposes_all_ios_decoded_fields(self) -> None:
        """Every field the iOS DTO decodes must appear on the response.

        Mirrors the iOS ``SubagentRestDTO`` field set. Missing fields would
        either silently drop data (e.g. summary → completion text lost) or
        force a coordinated iOS release to relax decoding.
        """
        user = _make_user_stub()
        spawned = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
        completed = spawned + timedelta(minutes=3)
        rows = [
            _make_subagent_row(
                session_id="sess-fields",
                task_id="t-fields",
                spawned_at=spawned,
                parent_session_id="parent-sess",
                name="developer",
                description="long description",
                prompt_preview="please do...",
                subagent_type="general-purpose",
                isolation="worktree",
                status="completed",
                summary="done",
                total_tokens=100,
                tool_uses=2,
                duration_ms=5000,
                updated_at=completed,
                completed_at=completed,
            ),
        ]
        _install_overrides(user)

        client = TestClient(app)
        with _patch_repo_listing({"sess-fields": rows}):
            resp = client.get("/api/v1/sessions/sess-fields/subagents")
        assert resp.status_code == 200, resp.text

        item = resp.json()[0]
        ios_decoded = {
            "id",
            "parent_id",
            "session_id",
            "status",
            "name",
            "description",
            "prompt_preview",
            "subagent_type",
            "isolation",
            "summary",
            "total_tokens",
            "tool_uses",
            "duration_ms",
            "activity",
            "started_at",
            "completed_at",
            "updated_at",
            "progress_percent",
        }
        missing = ios_decoded - set(item.keys())
        assert not missing, f"Endpoint missing iOS-decoded fields: {sorted(missing)}"

        # Spot-check non-trivial mappings.
        assert item["parent_id"] == "parent-sess"
        assert item["name"] == "developer"
        assert item["description"] == "long description"
        assert item["prompt_preview"] == "please do..."
        assert item["subagent_type"] == "general-purpose"
        assert item["isolation"] == "worktree"
        # activity + progress_percent are live-only — null on REST today.
        assert item["activity"] is None
        assert item["progress_percent"] is None

    def test_get_subagents_empty_returns_200_empty_list(self) -> None:
        """Unknown / empty session returns 200 with an empty array.

        The ``subagents`` table has no FK to ``sessions`` (the claude
        session id is a free-form string from the bridge stream parser),
        so we cannot meaningfully 404. iOS treats an empty list as
        "no subagents recorded yet" and falls back to live WS events.
        """
        user = _make_user_stub()
        _install_overrides(user)

        client = TestClient(app)
        with _patch_repo_listing({}):
            resp = client.get("/api/v1/sessions/never-existed/subagents")
        assert resp.status_code == 200, resp.text
        assert resp.json() == []

    def test_get_subagents_does_not_leak_other_sessions(self) -> None:
        """Sibling-session rows MUST NOT bleed into the response."""
        user = _make_user_stub()
        base = datetime.now(tz=UTC)
        rows_by_session = {
            "sess-mine": [
                _make_subagent_row(
                    session_id="sess-mine",
                    task_id="mine-1",
                    spawned_at=base,
                ),
            ],
            "sess-noise": [
                _make_subagent_row(
                    session_id="sess-noise",
                    task_id="noise-1",
                    spawned_at=base,
                ),
            ],
        }
        _install_overrides(user)

        client = TestClient(app)
        with _patch_repo_listing(rows_by_session):
            resp = client.get("/api/v1/sessions/sess-mine/subagents")
        assert resp.status_code == 200, resp.text

        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == "mine-1"
        assert data[0]["session_id"] == "sess-mine"

    def test_get_subagents_response_has_iso_timestamps(self) -> None:
        """``started_at`` and ``completed_at`` serialise as ISO 8601 strings."""
        user = _make_user_stub()
        spawned = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
        completed = spawned + timedelta(minutes=2)
        rows = [
            _make_subagent_row(
                session_id="sess-iso",
                task_id="t-iso",
                spawned_at=spawned,
                completed_at=completed,
                status="completed",
            ),
        ]
        _install_overrides(user)

        client = TestClient(app)
        with _patch_repo_listing({"sess-iso": rows}):
            resp = client.get("/api/v1/sessions/sess-iso/subagents")
        assert resp.status_code == 200, resp.text

        item: dict[str, Any] = resp.json()[0]
        # Round-trip the timestamps to confirm they're parseable.
        parsed_started = datetime.fromisoformat(item["started_at"].replace("Z", "+00:00"))
        parsed_completed = datetime.fromisoformat(item["completed_at"].replace("Z", "+00:00"))
        assert parsed_started == spawned
        assert parsed_completed == completed
