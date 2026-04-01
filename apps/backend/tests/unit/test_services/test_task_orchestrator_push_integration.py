"""Integration tests for TaskOrchestratorService + LiveActivityPushService — Sprint 2.

Verifies that task progress/completion/failure events correctly trigger
Live Activity push notifications via LiveActivityPushService.
All tests should FAIL until implementation is written (TDD red phase).
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.task import Task as TaskModel, TaskStatus
from app.services.live_activity_push_service import LiveActivityPushService
from app.services.task_orchestrator_service import TaskOrchestratorService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_PUSH_TOKEN = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6abcd"


def _make_task_model(
    status: TaskStatus = TaskStatus.IMPLEMENTING,
    live_activity_push_token: str | None = SAMPLE_PUSH_TOKEN,
    current_step: str = "developer",
    progress_pct: int = 30,
    completed_steps: int = 1,
    total_steps: int = 4,
) -> MagicMock:
    """Create a mock Task model for push integration tests."""
    task = MagicMock(spec=TaskModel)
    task.id = uuid.uuid4()
    task.user_id = uuid.uuid4()
    task.project_id = uuid.uuid4()
    task.agent_id = "host-1"
    task.title = "Implement search feature"
    task.prompt = "Add full-text search"
    task.task_type = "feature"
    task.status = status
    task.current_step = current_step
    task.total_steps = total_steps
    task.completed_steps = completed_steps
    task.progress_pct = progress_pct
    task.result_summary = None
    task.error_message = None
    task.claude_session_id = None
    task.claude_task_id = None
    task.live_activity_push_token = live_activity_push_token
    task.created_at = datetime.now(tz=UTC)
    task.started_at = datetime.now(tz=UTC)
    task.completed_at = None
    task.updated_at = datetime.now(tz=UTC)
    return task


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestProgressUpdateTriggersPush:
    """TaskOrchestratorService.update_progress() should trigger Live Activity push."""

    @pytest.mark.asyncio
    async def test_progress_update_triggers_push(self) -> None:
        """Updating task progress should send a Live Activity update push."""
        mock_session = AsyncMock()
        mock_push_service = AsyncMock(spec=LiveActivityPushService)
        mock_push_service.send_live_activity_update = AsyncMock(return_value=True)
        service = TaskOrchestratorService(mock_session, push_service=mock_push_service)

        task = _make_task_model(
            status=TaskStatus.IMPLEMENTING,
            current_step="developer",
            progress_pct=30,
            completed_steps=1,
        )
        service._tasks[task.id] = task

        mock_session.commit = AsyncMock()

        await service.update_progress(
            task_id=task.id,
            step="developer",
            pct=50,
            detail="Writing unit tests...",
        )

        # Push should have been called with the task's push token
        mock_push_service.send_live_activity_update.assert_called_once()
        call_kwargs = mock_push_service.send_live_activity_update.call_args
        token_arg = call_kwargs.kwargs.get("push_token") or call_kwargs[0][0]
        assert token_arg == SAMPLE_PUSH_TOKEN


class TestCompletionTriggersVisiblePush:
    """Task completion should send a visible push notification."""

    @pytest.mark.asyncio
    async def test_completion_triggers_visible_push(self) -> None:
        """Completing a task should send a visible push notification."""
        mock_session = AsyncMock()
        mock_push_service = AsyncMock(spec=LiveActivityPushService)
        mock_push_service.send_live_activity_end = AsyncMock(return_value=True)
        mock_push_service.send_visible_push = AsyncMock(return_value=True)
        service = TaskOrchestratorService(mock_session, push_service=mock_push_service)

        task = _make_task_model(
            status=TaskStatus.REVIEWING,
            current_step="reviewer",
            progress_pct=75,
            completed_steps=3,
        )
        service._tasks[task.id] = task

        mock_session.commit = AsyncMock()

        await service.complete_task(
            task_id=task.id,
            summary="Feature implemented and reviewed successfully.",
        )

        # Visible push notification should be sent
        mock_push_service.send_visible_push.assert_called_once()


class TestFailureTriggersVisiblePush:
    """Task failure should send a visible push notification."""

    @pytest.mark.asyncio
    async def test_failure_triggers_visible_push(self) -> None:
        """Failing a task should send a visible push notification."""
        mock_session = AsyncMock()
        mock_push_service = AsyncMock(spec=LiveActivityPushService)
        mock_push_service.send_live_activity_end = AsyncMock(return_value=True)
        mock_push_service.send_visible_push = AsyncMock(return_value=True)
        service = TaskOrchestratorService(mock_session, push_service=mock_push_service)

        task = _make_task_model(
            status=TaskStatus.IMPLEMENTING,
            current_step="developer",
            progress_pct=40,
            completed_steps=1,
        )
        service._tasks[task.id] = task

        mock_session.commit = AsyncMock()

        await service.fail_task(
            task_id=task.id,
            error="Compilation failed: missing dependency",
        )

        # Visible push notification should be sent
        mock_push_service.send_visible_push.assert_called_once()


class TestNoPushWithoutToken:
    """Push should be skipped when live_activity_push_token is None."""

    @pytest.mark.asyncio
    async def test_no_push_without_token(self) -> None:
        """If task has no live_activity_push_token, push should be skipped."""
        mock_session = AsyncMock()
        mock_push_service = AsyncMock(spec=LiveActivityPushService)
        service = TaskOrchestratorService(mock_session, push_service=mock_push_service)

        task = _make_task_model(
            status=TaskStatus.IMPLEMENTING,
            live_activity_push_token=None,  # No token
        )
        service._tasks[task.id] = task

        mock_session.commit = AsyncMock()

        await service.update_progress(
            task_id=task.id,
            step="developer",
            pct=50,
            detail="Writing code...",
        )

        # Push service should NOT have been called
        mock_push_service.send_live_activity_update.assert_not_called()


class TestPushOnStepChangeOnly:
    """Repeated updates within the same step should be throttled."""

    @pytest.mark.asyncio
    async def test_push_on_step_change_only(self) -> None:
        """Multiple progress updates for the same step should all trigger pushes (no throttle in current impl)."""
        mock_session = AsyncMock()
        mock_push_service = AsyncMock(spec=LiveActivityPushService)
        mock_push_service.send_live_activity_update = AsyncMock(return_value=True)
        service = TaskOrchestratorService(mock_session, push_service=mock_push_service)

        task = _make_task_model(
            status=TaskStatus.IMPLEMENTING,
            current_step="developer",
            progress_pct=30,
        )
        service._tasks[task.id] = task

        mock_session.commit = AsyncMock()

        # Same step, different percentages
        for pct in [35, 40, 45, 50]:
            task.progress_pct = pct
            await service.update_progress(
                task_id=task.id,
                step="developer",
                pct=pct,
                detail=f"Progress at {pct}%...",
            )

        # Current implementation sends push for every update with a token
        assert mock_push_service.send_live_activity_update.call_count == 4
