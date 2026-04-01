"""Unit tests for Task REST API routes — Sprint 1 Faz A.

Tests the /api/v1/tasks/* endpoints: creation, retrieval,
cancellation, live-activity token registration, history pagination,
and authorization guards.
All tests should FAIL until implementation is written (TDD red phase).
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import TaskStatus


# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------

def _fake_task(
    task_id: uuid.UUID | None = None,
    status: TaskStatus = TaskStatus.QUEUED,
    title: str = "Implement voice input",
    prompt: str = "Add voice input feature",
    task_type: str = "feature",
    progress_pct: int = 0,
    completed_steps: int = 0,
    total_steps: int = 4,
    current_step: str | None = None,
    result_summary: str | None = None,
    error_message: str | None = None,
    live_activity_push_token: str | None = None,
) -> MagicMock:
    """Return a mock object that looks like a TaskResponse schema."""
    t = MagicMock()
    t.id = task_id or uuid.uuid4()
    t.user_id = uuid.uuid4()
    t.project_id = None
    t.agent_id = None
    t.title = title
    t.prompt = prompt
    t.task_type = task_type
    t.status = status
    t.current_step = current_step
    t.total_steps = total_steps
    t.completed_steps = completed_steps
    t.progress_pct = progress_pct
    t.result_summary = result_summary
    t.error_message = error_message
    t.claude_session_id = None
    t.claude_task_id = None
    t.live_activity_push_token = live_activity_push_token
    t.created_at = datetime.now(tz=UTC)
    t.started_at = None
    t.completed_at = None
    t.updated_at = datetime.now(tz=UTC)
    return t


@pytest.fixture()
def mock_db() -> AsyncMock:
    """Mock AsyncSession."""
    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock(return_value=MagicMock())
    return session


@pytest.fixture()
def auth_headers() -> dict[str, str]:
    """Return a valid JWT Authorization header for testing.

    The actual JWT validation should be mocked; this fixture provides
    the header shape so the auth dependency can be overridden.
    """
    return {"Authorization": "Bearer test-jwt-token"}


def _make_client(
    mock_db: AsyncMock,
    current_user_id: uuid.UUID | None = None,
) -> TestClient:
    """Create a TestClient with mocked DB and auth dependencies."""
    from app.main import app
    from app.api.deps import get_db, get_current_user

    async def override_get_db():  # type: ignore[no-untyped-def]
        yield mock_db

    user_id = current_user_id or uuid.uuid4()

    async def override_get_current_user():  # type: ignore[no-untyped-def]
        user = MagicMock()
        user.id = user_id
        return user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    return TestClient(app)


def _cleanup_overrides() -> None:
    from app.main import app
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# POST /api/v1/tasks
# ---------------------------------------------------------------------------

class TestCreateTask:
    """Tests for POST /api/v1/tasks."""

    def test_create_task_201(self, mock_db: AsyncMock, auth_headers: dict[str, str]) -> None:
        """Should create a task and return 201 with task data."""
        task = _fake_task(status=TaskStatus.QUEUED)

        with patch(
            "app.api.routes.tasks.TaskOrchestratorService",
        ) as MockService:
            instance = MockService.return_value
            instance.create_task = AsyncMock(return_value=task)

            client = _make_client(mock_db)
            try:
                response = client.post(
                    "/api/v1/tasks",
                    json={
                        "prompt": "Add voice input feature",
                        "task_type": "feature",
                        "project_id": None,
                    },
                    headers=auth_headers,
                )
            finally:
                _cleanup_overrides()

        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "queued"
        assert data["prompt"] == "Add voice input feature"
        assert "id" in data


# ---------------------------------------------------------------------------
# GET /api/v1/tasks/active
# ---------------------------------------------------------------------------

class TestGetActiveTasks:
    """Tests for GET /api/v1/tasks/active."""

    def test_get_active_tasks_200(self, mock_db: AsyncMock, auth_headers: dict[str, str]) -> None:
        """Should return a list of active (non-terminal) tasks."""
        tasks = [
            _fake_task(status=TaskStatus.IMPLEMENTING, current_step="developer", progress_pct=45),
            _fake_task(status=TaskStatus.QUEUED),
        ]

        with patch(
            "app.api.routes.tasks.TaskOrchestratorService",
        ) as MockService:
            instance = MockService.return_value
            instance.get_active_tasks = AsyncMock(return_value=tasks)

            client = _make_client(mock_db)
            try:
                response = client.get(
                    "/api/v1/tasks/active",
                    headers=auth_headers,
                )
            finally:
                _cleanup_overrides()

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 2


# ---------------------------------------------------------------------------
# GET /api/v1/tasks/{id}
# ---------------------------------------------------------------------------

class TestGetTaskDetail:
    """Tests for GET /api/v1/tasks/{id}."""

    def test_get_task_detail_200(self, mock_db: AsyncMock, auth_headers: dict[str, str]) -> None:
        """Should return task detail for a valid task id."""
        task_id = uuid.uuid4()
        user_id = uuid.uuid4()
        task = _fake_task(task_id=task_id, status=TaskStatus.IMPLEMENTING, progress_pct=60)
        task.user_id = user_id

        with patch(
            "app.api.routes.tasks.TaskOrchestratorService",
        ) as MockService:
            instance = MockService.return_value
            instance.get_task = AsyncMock(return_value=task)

            client = _make_client(mock_db, current_user_id=user_id)
            try:
                response = client.get(
                    f"/api/v1/tasks/{task_id}",
                    headers=auth_headers,
                )
            finally:
                _cleanup_overrides()

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(task_id)
        assert data["progress_pct"] == 60

    def test_get_task_404(self, mock_db: AsyncMock, auth_headers: dict[str, str]) -> None:
        """Should return 404 when task does not exist."""
        task_id = uuid.uuid4()

        with patch(
            "app.api.routes.tasks.TaskOrchestratorService",
        ) as MockService:
            instance = MockService.return_value
            instance.get_task = AsyncMock(return_value=None)

            client = _make_client(mock_db)
            try:
                response = client.get(
                    f"/api/v1/tasks/{task_id}",
                    headers=auth_headers,
                )
            finally:
                _cleanup_overrides()

        assert response.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/v1/tasks/{id}/cancel
# ---------------------------------------------------------------------------

class TestCancelTask:
    """Tests for POST /api/v1/tasks/{id}/cancel."""

    def test_cancel_task_200(self, mock_db: AsyncMock, auth_headers: dict[str, str]) -> None:
        """Should cancel an active task and return 200."""
        task_id = uuid.uuid4()
        user_id = uuid.uuid4()
        existing_task = _fake_task(task_id=task_id, status=TaskStatus.IMPLEMENTING)
        existing_task.user_id = user_id
        cancelled_task = _fake_task(task_id=task_id, status=TaskStatus.CANCELLED)
        cancelled_task.user_id = user_id

        with patch(
            "app.api.routes.tasks.TaskOrchestratorService",
        ) as MockService:
            instance = MockService.return_value
            instance.get_task = AsyncMock(return_value=existing_task)
            instance.cancel_task = AsyncMock(return_value=cancelled_task)

            client = _make_client(mock_db, current_user_id=user_id)
            try:
                response = client.post(
                    f"/api/v1/tasks/{task_id}/cancel",
                    headers=auth_headers,
                )
            finally:
                _cleanup_overrides()

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "cancelled"

    def test_cancel_completed_task_409(self, mock_db: AsyncMock, auth_headers: dict[str, str]) -> None:
        """Should return 409 when trying to cancel a completed task."""
        task_id = uuid.uuid4()
        user_id = uuid.uuid4()
        existing_task = _fake_task(task_id=task_id, status=TaskStatus.COMPLETED)
        existing_task.user_id = user_id

        with patch(
            "app.api.routes.tasks.TaskOrchestratorService",
        ) as MockService:
            instance = MockService.return_value
            instance.get_task = AsyncMock(return_value=existing_task)
            instance.cancel_task = AsyncMock(
                side_effect=ValueError("Cannot cancel a completed task"),
            )

            client = _make_client(mock_db, current_user_id=user_id)
            try:
                response = client.post(
                    f"/api/v1/tasks/{task_id}/cancel",
                    headers=auth_headers,
                )
            finally:
                _cleanup_overrides()

        assert response.status_code == 409


# ---------------------------------------------------------------------------
# PATCH /api/v1/tasks/{id}/live-activity
# ---------------------------------------------------------------------------

class TestRegisterLiveActivityToken:
    """Tests for PATCH /api/v1/tasks/{id}/live-activity."""

    def test_register_live_activity_token_200(
        self, mock_db: AsyncMock, auth_headers: dict[str, str],
    ) -> None:
        """Should save a push token and return 200."""
        task_id = uuid.uuid4()
        user_id = uuid.uuid4()
        token = "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
        existing_task = _fake_task(task_id=task_id, status=TaskStatus.IMPLEMENTING)
        existing_task.user_id = user_id
        updated_task = _fake_task(
            task_id=task_id,
            status=TaskStatus.IMPLEMENTING,
            live_activity_push_token=token,
        )
        updated_task.user_id = user_id

        with patch(
            "app.api.routes.tasks.TaskOrchestratorService",
        ) as MockService:
            instance = MockService.return_value
            instance.get_task = AsyncMock(return_value=existing_task)
            instance.register_live_activity_token = AsyncMock(return_value=updated_task)

            client = _make_client(mock_db, current_user_id=user_id)
            try:
                response = client.patch(
                    f"/api/v1/tasks/{task_id}/live-activity",
                    json={"push_token": token},
                    headers=auth_headers,
                )
            finally:
                _cleanup_overrides()

        assert response.status_code == 200
        data = response.json()
        assert data["has_live_activity_token"] is True


# ---------------------------------------------------------------------------
# GET /api/v1/tasks/history
# ---------------------------------------------------------------------------

class TestTaskHistory:
    """Tests for GET /api/v1/tasks/history (paginated)."""

    def test_task_history_paginated(
        self, mock_db: AsyncMock, auth_headers: dict[str, str],
    ) -> None:
        """Should return paginated completed/failed/cancelled tasks."""
        tasks = [
            _fake_task(status=TaskStatus.COMPLETED, result_summary="Done"),
            _fake_task(status=TaskStatus.FAILED, error_message="Compilation error"),
        ]

        with patch(
            "app.api.routes.tasks.TaskOrchestratorService",
        ) as MockService:
            instance = MockService.return_value
            instance.get_task_history = AsyncMock(
                return_value={"tasks": tasks, "total": 2, "page": 1, "page_size": 20},
            )

            client = _make_client(mock_db)
            try:
                response = client.get(
                    "/api/v1/tasks/history?page=1&size=20",
                    headers=auth_headers,
                )
            finally:
                _cleanup_overrides()

        assert response.status_code == 200
        data = response.json()
        assert "tasks" in data or isinstance(data, list)
        # Should contain only terminal tasks
        assert data["total"] == 2 or len(data) == 2


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------

class TestAuthorization:
    """Tests for JWT authorization enforcement."""

    def test_unauthorized_401(self, mock_db: AsyncMock) -> None:
        """Should return 401 when no JWT token is provided."""
        from app.main import app
        from app.api.deps import get_db

        async def override_get_db():  # type: ignore[no-untyped-def]
            yield mock_db

        # Override DB but NOT the auth dependency — so real auth runs
        app.dependency_overrides[get_db] = override_get_db

        client = TestClient(app)
        try:
            # No Authorization header
            response = client.get("/api/v1/tasks/active")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 401
