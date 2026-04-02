"""Unit tests for TaskOrchestratorService — Sprint 1 Faz A.

Tests the task lifecycle state machine: creation, transitions,
progress updates, completion, failure, cancellation, and querying.
All tests should FAIL until implementation is written (TDD red phase).
"""

import asyncio
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.task import Task as TaskModel, TaskStatus
from app.services.task_orchestrator_service import TaskOrchestratorService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_task_model(
    status: TaskStatus = TaskStatus.QUEUED,
    user_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    agent_id: str | None = None,
    title: str = "Implement voice input",
    prompt: str = "Add voice input feature",
    task_type: str = "feature",
    current_step: str | None = None,
    total_steps: int = 4,
    completed_steps: int = 0,
    progress_pct: int = 0,
    result_summary: str | None = None,
    error_message: str | None = None,
    live_activity_push_token: str | None = None,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
) -> MagicMock:
    """Create a mock Task SQLAlchemy model for testing."""
    task = MagicMock(spec=TaskModel)
    task.id = uuid.uuid4()
    task.user_id = user_id or uuid.uuid4()
    task.project_id = project_id
    task.agent_id = agent_id
    task.title = title
    task.prompt = prompt
    task.task_type = task_type
    task.status = status
    task.current_step = current_step
    task.total_steps = total_steps
    task.completed_steps = completed_steps
    task.progress_pct = progress_pct
    task.result_summary = result_summary
    task.error_message = error_message
    task.claude_session_id = None
    task.claude_task_id = None
    task.live_activity_push_token = live_activity_push_token
    task.created_at = datetime.now(tz=UTC)
    task.started_at = started_at
    task.completed_at = completed_at
    task.updated_at = datetime.now(tz=UTC)
    return task


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCreateTask:
    """Tests for TaskOrchestratorService.create_task."""

    async def test_create_task(self) -> None:
        """Should create a task with QUEUED status and correct fields."""
        mock_session = AsyncMock()
        service = TaskOrchestratorService(mock_session)

        user_id = uuid.uuid4()
        project_id = uuid.uuid4()

        result = await service.create_task(
            user_id=user_id,
            project_id=project_id,
            prompt="Add voice input feature",
            task_type="feature",
        )

        assert result.status == TaskStatus.QUEUED
        assert result.user_id == user_id
        assert result.project_id == project_id
        assert result.prompt == "Add voice input feature"
        assert result.task_type == "feature"
        assert result.progress_pct == 0
        assert result.completed_steps == 0
        assert result.completed_at is None
        assert result.started_at is None


class TestStartTask:
    """Tests for TaskOrchestratorService.start_task."""

    async def test_start_task(self) -> None:
        """Should transition QUEUED -> PLANNING and set started_at."""
        mock_session = AsyncMock()
        service = TaskOrchestratorService(mock_session)

        task = _make_task_model(status=TaskStatus.QUEUED)
        service._tasks[task.id] = task

        result = await service.start_task(task.id)

        assert result.status == TaskStatus.PLANNING
        assert result.started_at is not None
        assert result.current_step == "architect"


class TestInvalidTransition:
    """Tests for state transition guard rejections."""

    async def test_invalid_transition(self) -> None:
        """Should reject COMPLETED -> PLANNING transition with an error."""
        mock_session = AsyncMock()
        service = TaskOrchestratorService(mock_session)

        task = _make_task_model(status=TaskStatus.COMPLETED)
        service._tasks[task.id] = task

        with pytest.raises(ValueError, match="[Ii]nvalid.*transition"):
            await service.start_task(task.id)

    async def test_failed_to_planning_rejected(self) -> None:
        """Should reject FAILED -> PLANNING transition."""
        mock_session = AsyncMock()
        service = TaskOrchestratorService(mock_session)

        task = _make_task_model(status=TaskStatus.FAILED)
        service._tasks[task.id] = task

        with pytest.raises(ValueError, match="[Ii]nvalid.*transition"):
            await service.start_task(task.id)

    async def test_cancelled_to_implementing_rejected(self) -> None:
        """Should reject CANCELLED -> any active transition."""
        mock_session = AsyncMock()
        service = TaskOrchestratorService(mock_session)

        task = _make_task_model(status=TaskStatus.CANCELLED)
        service._tasks[task.id] = task

        with pytest.raises(ValueError, match="[Ii]nvalid.*transition"):
            await service.start_task(task.id)


class TestUpdateProgress:
    """Tests for TaskOrchestratorService.update_progress."""

    async def test_update_progress(self) -> None:
        """Should update progress_pct, current_step, and completed_steps."""
        mock_session = AsyncMock()
        service = TaskOrchestratorService(mock_session)

        task = _make_task_model(
            status=TaskStatus.IMPLEMENTING,
            current_step="developer",
            completed_steps=1,
            progress_pct=25,
        )
        service._tasks[task.id] = task

        result = await service.update_progress(
            task_id=task.id,
            step="developer",
            pct=50,
            detail="Creating VoiceInputView.swift...",
        )

        assert result.progress_pct == 50
        assert result.current_step == "developer"

    async def test_update_progress_clamps_pct(self) -> None:
        """Should clamp progress_pct between 0 and 100."""
        mock_session = AsyncMock()
        service = TaskOrchestratorService(mock_session)

        task = _make_task_model(status=TaskStatus.IMPLEMENTING)
        service._tasks[task.id] = task

        result = await service.update_progress(
            task_id=task.id,
            step="developer",
            pct=150,
            detail="Over max",
        )

        assert result.progress_pct <= 100


class TestCompleteTask:
    """Tests for TaskOrchestratorService.complete_task."""

    async def test_complete_task(self) -> None:
        """Should set status=COMPLETED, completed_at, and result_summary."""
        mock_session = AsyncMock()
        service = TaskOrchestratorService(mock_session)

        task = _make_task_model(status=TaskStatus.REVIEWING)
        service._tasks[task.id] = task

        result = await service.complete_task(
            task_id=task.id,
            summary="Feature implemented and all tests pass.",
        )

        assert result.status == TaskStatus.COMPLETED
        assert result.completed_at is not None
        assert result.result_summary == "Feature implemented and all tests pass."
        assert result.progress_pct == 100


class TestFailTask:
    """Tests for TaskOrchestratorService.fail_task."""

    async def test_fail_task(self) -> None:
        """Should set status=FAILED and error_message."""
        mock_session = AsyncMock()
        service = TaskOrchestratorService(mock_session)

        task = _make_task_model(status=TaskStatus.IMPLEMENTING)
        service._tasks[task.id] = task

        result = await service.fail_task(
            task_id=task.id,
            error="Compilation failed: missing module",
        )

        assert result.status == TaskStatus.FAILED
        assert result.error_message == "Compilation failed: missing module"
        assert result.completed_at is not None


class TestCancelTask:
    """Tests for TaskOrchestratorService.cancel_task."""

    async def test_cancel_task(self) -> None:
        """Should set status=CANCELLED for an active task."""
        mock_session = AsyncMock()
        service = TaskOrchestratorService(mock_session)

        task = _make_task_model(status=TaskStatus.TESTING)
        service._tasks[task.id] = task

        result = await service.cancel_task(task.id)

        assert result.status == TaskStatus.CANCELLED

    async def test_cancel_completed_task_raises(self) -> None:
        """Should reject cancellation of an already completed task."""
        mock_session = AsyncMock()
        service = TaskOrchestratorService(mock_session)

        task = _make_task_model(status=TaskStatus.COMPLETED)
        service._tasks[task.id] = task

        with pytest.raises(ValueError, match="[Cc]annot cancel|[Ii]nvalid"):
            await service.cancel_task(task.id)


class TestGetActiveTasks:
    """Tests for TaskOrchestratorService.get_active_tasks."""

    async def test_get_active_tasks(self) -> None:
        """Should return only running (non-terminal) tasks for a user."""
        mock_session = AsyncMock()
        service = TaskOrchestratorService(mock_session)

        user_id = uuid.uuid4()
        active_task = _make_task_model(status=TaskStatus.IMPLEMENTING, user_id=user_id)
        queued_task = _make_task_model(status=TaskStatus.QUEUED, user_id=user_id)

        # Mock the DB execute → scalars → all chain
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [active_task, queued_task]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await service.get_active_tasks(user_id)

        # Only non-terminal tasks should be returned
        for task in result:
            assert task.status not in (
                TaskStatus.COMPLETED,
                TaskStatus.FAILED,
                TaskStatus.CANCELLED,
            )

    async def test_get_active_tasks_empty(self) -> None:
        """Should return empty list when user has no active tasks."""
        mock_session = AsyncMock()
        service = TaskOrchestratorService(mock_session)

        user_id = uuid.uuid4()

        # Mock the DB execute → scalars → all chain returning empty
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await service.get_active_tasks(user_id)

        assert result == []


class TestRegisterLiveActivityToken:
    """Tests for TaskOrchestratorService.register_live_activity_token."""

    async def test_register_live_activity_token(self) -> None:
        """Should save push token on the task."""
        mock_session = AsyncMock()
        service = TaskOrchestratorService(mock_session)

        task = _make_task_model(status=TaskStatus.IMPLEMENTING)
        token = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6abcd"
        service._tasks[task.id] = task

        result = await service.register_live_activity_token(
            task_id=task.id,
            token=token,
        )

        assert result.live_activity_push_token == token


class TestStateTransitionsCompleteFlow:
    """Tests for the full state transition path."""

    async def test_state_transitions_complete_flow(self) -> None:
        """Should successfully traverse QUEUED -> PLANNING -> IMPLEMENTING -> TESTING -> REVIEWING -> COMPLETED."""
        mock_session = AsyncMock()
        service = TaskOrchestratorService(mock_session)

        user_id = uuid.uuid4()

        # Create task (QUEUED)
        task = await service.create_task(
            user_id=user_id,
            project_id=None,
            prompt="Build full feature",
            task_type="feature",
        )
        assert task.status == TaskStatus.QUEUED

        # QUEUED -> PLANNING
        task = await service.start_task(task.id)
        assert task.status == TaskStatus.PLANNING

        # PLANNING -> IMPLEMENTING
        task.status = TaskStatus.PLANNING
        task = await service.update_progress(
            task_id=task.id,
            step="developer",
            pct=25,
            detail="Architect complete, developer starting",
        )
        assert task.status == TaskStatus.IMPLEMENTING or task.current_step == "developer"

        # IMPLEMENTING -> TESTING
        task.status = TaskStatus.IMPLEMENTING
        task = await service.update_progress(
            task_id=task.id,
            step="tester",
            pct=50,
            detail="Developer complete, tester starting",
        )

        # TESTING -> REVIEWING
        task.status = TaskStatus.TESTING
        task = await service.update_progress(
            task_id=task.id,
            step="reviewer",
            pct=75,
            detail="Tester complete, reviewer starting",
        )

        # REVIEWING -> COMPLETED
        task.status = TaskStatus.REVIEWING
        task = await service.complete_task(
            task_id=task.id,
            summary="All steps passed.",
        )
        assert task.status == TaskStatus.COMPLETED
        assert task.progress_pct == 100
        assert task.completed_at is not None


class TestConcurrentTaskUpdates:
    """Tests for concurrent update safety."""

    async def test_concurrent_task_updates(self) -> None:
        """Should handle concurrent progress updates without data corruption."""
        mock_session = AsyncMock()
        service = TaskOrchestratorService(mock_session)

        task = _make_task_model(status=TaskStatus.IMPLEMENTING)
        service._tasks[task.id] = task

        # Fire multiple concurrent updates
        updates = [
            service.update_progress(task.id, "developer", pct, f"Step {pct}")
            for pct in (10, 20, 30, 40, 50)
        ]
        results = await asyncio.gather(*updates, return_exceptions=True)

        # All should succeed (no unhandled exceptions)
        for r in results:
            assert not isinstance(r, Exception), f"Update raised: {r}"
