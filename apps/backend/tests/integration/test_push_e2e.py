"""End-to-end integration tests for Push Notification / Live Activity — Sprint 5.

These tests verify APNs Live Activity push on progress, visible push on
completion, and push token cleanup when APNs returns 410 Gone.
All tests are expected to FAIL until implementation is complete.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.task import Task, TaskStatus
from app.services.task_orchestrator_service import TaskOrchestratorService
from app.services.live_activity_push_service import LiveActivityPushService
from app.services.apns_client import send_push


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db_session() -> AsyncMock:
    """Provide a mock async database session."""
    session = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.execute = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def mock_agent_registry() -> AsyncMock:
    """Provide a mock BridgeRegistryService."""
    registry = AsyncMock()
    registry.get_agent = AsyncMock(return_value={
        "host_id": "macbook-pro",
        "status": "online",
        "last_heartbeat": datetime.now(tz=timezone.utc),
    })
    return registry


@pytest.fixture
def mock_push_service() -> AsyncMock:
    """Provide a mock LiveActivityPushService with controllable responses."""
    push = AsyncMock(spec=LiveActivityPushService)
    push.send_live_activity_update = AsyncMock(return_value={"status": 200})
    push.send_visible_push = AsyncMock(return_value={"status": 200})
    return push


@pytest.fixture
def mock_ws_manager() -> AsyncMock:
    ws = AsyncMock()
    ws.broadcast_to_user = AsyncMock()
    return ws


@pytest.fixture
def orchestrator(
    mock_db_session: AsyncMock,
    mock_agent_registry: AsyncMock,
    mock_push_service: AsyncMock,
    mock_ws_manager: AsyncMock,
) -> TaskOrchestratorService:
    return TaskOrchestratorService(
        db=mock_db_session,
        agent_registry=mock_agent_registry,
        push_service=mock_push_service,
        ws_manager=mock_ws_manager,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_LIVE_ACTIVITY_TOKEN = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6abcd"
FAKE_DEVICE_PUSH_TOKEN = "ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00abcd"


def _make_user_id() -> uuid.UUID:
    return uuid.uuid4()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestLiveActivityPushOnProgress:
    """test_live_activity_push_sent_on_progress."""

    @pytest.mark.asyncio
    async def test_live_activity_push_sent_on_progress(
        self,
        orchestrator: TaskOrchestratorService,
        mock_push_service: AsyncMock,
    ) -> None:
        """When a task with a registered Live Activity push token has its
        progress updated, an APNs Live Activity push should be sent with
        the correct content-state payload."""

        user_id = _make_user_id()

        task = await orchestrator.create_task(
            user_id=user_id,
            project_id=None,
            prompt="Build CI pipeline",
            task_type="feature",
        )

        # Register Live Activity push token
        await orchestrator.register_live_activity_token(
            task_id=task.id,
            token=FAKE_LIVE_ACTIVITY_TOKEN,
        )

        await orchestrator.start_task(task.id)

        # Update progress — should trigger APNs Live Activity push
        await orchestrator.update_progress(
            task_id=task.id,
            step="developer",
            pct=45,
            detail="Creating pipeline YAML...",
        )

        mock_push_service.send_live_activity_update.assert_awaited()

        call_args = mock_push_service.send_live_activity_update.call_args
        assert call_args is not None

        # Verify push token is passed
        token_arg = call_args[0][0] if call_args[0] else call_args[1].get("push_token")
        assert token_arg == FAKE_LIVE_ACTIVITY_TOKEN

        # Verify content-state fields
        content_state = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("content_state")
        assert content_state["status"] == "implementing"
        assert content_state["progress"] == 0.45 or content_state["progress_pct"] == 45
        assert content_state["currentStep"] == "developer" or content_state["current_step"] == "developer"

        # Verify event type is "update" (not "end")
        event = call_args[0][2] if len(call_args[0]) > 2 else call_args[1].get("event")
        assert event == "update"

    @pytest.mark.asyncio
    async def test_no_push_when_no_live_activity_token(
        self,
        orchestrator: TaskOrchestratorService,
        mock_push_service: AsyncMock,
    ) -> None:
        """When a task does NOT have a Live Activity push token registered,
        updating progress should NOT attempt to send an APNs push."""

        user_id = _make_user_id()

        task = await orchestrator.create_task(
            user_id=user_id,
            project_id=None,
            prompt="Update readme",
            task_type="docs",
        )
        await orchestrator.start_task(task.id)

        await orchestrator.update_progress(
            task_id=task.id,
            step="developer",
            pct=50,
            detail="Editing docs...",
        )

        # Live Activity push should NOT be called (no token)
        mock_push_service.send_live_activity_update.assert_not_awaited()


class TestVisiblePushOnCompletion:
    """test_visible_push_on_completion."""

    @pytest.mark.asyncio
    async def test_visible_push_on_completion(
        self,
        orchestrator: TaskOrchestratorService,
        mock_push_service: AsyncMock,
        mock_db_session: AsyncMock,
    ) -> None:
        """When a task completes, a visible push notification should be sent
        with a human-readable title and body (not just a silent content-state)."""

        user_id = _make_user_id()

        task = await orchestrator.create_task(
            user_id=user_id,
            project_id=None,
            prompt="Add dark mode",
            task_type="feature",
        )
        await orchestrator.start_task(task.id)

        await orchestrator.complete_task(
            task_id=task.id,
            summary="Dark mode implemented and merged.",
        )

        # Visible push should be sent
        mock_push_service.send_visible_push.assert_awaited()

        call_args = mock_push_service.send_visible_push.call_args
        assert call_args is not None

        # Extract title and body from the push call
        push_kwargs = call_args[1] if call_args[1] else {}
        push_args = call_args[0] if call_args[0] else ()

        # Title and body should be present (positional or keyword)
        if push_args:
            # Expecting (user_id, title, body) or similar
            assert len(push_args) >= 2
            title = push_args[1] if len(push_args) > 1 else push_kwargs.get("title")
            body = push_args[2] if len(push_args) > 2 else push_kwargs.get("body")
        else:
            title = push_kwargs.get("title")
            body = push_kwargs.get("body")

        assert title is not None, "Push notification must have a title"
        assert body is not None, "Push notification must have a body"
        assert len(title) > 0
        assert len(body) > 0

    @pytest.mark.asyncio
    async def test_visible_push_on_failure(
        self,
        orchestrator: TaskOrchestratorService,
        mock_push_service: AsyncMock,
    ) -> None:
        """When a task fails, a visible push notification should also be sent
        to alert the user."""

        user_id = _make_user_id()

        task = await orchestrator.create_task(
            user_id=user_id,
            project_id=None,
            prompt="Deploy to production",
            task_type="feature",
        )
        await orchestrator.start_task(task.id)

        await orchestrator.fail_task(
            task_id=task.id,
            error="Docker build failed: exit code 1",
        )

        mock_push_service.send_visible_push.assert_awaited()


class TestTokenCleanupOnInvalid:
    """test_token_cleanup_on_invalid — APNs 410 Gone triggers DB cleanup."""

    @pytest.mark.asyncio
    async def test_token_cleanup_on_apns_410(
        self,
        orchestrator: TaskOrchestratorService,
        mock_push_service: AsyncMock,
        mock_db_session: AsyncMock,
    ) -> None:
        """When APNs returns 410 Gone for a push token, the token should be
        removed from the database so we don't keep sending to it."""

        user_id = _make_user_id()

        task = await orchestrator.create_task(
            user_id=user_id,
            project_id=None,
            prompt="Run integration tests",
            task_type="feature",
        )

        await orchestrator.register_live_activity_token(
            task_id=task.id,
            token=FAKE_LIVE_ACTIVITY_TOKEN,
        )
        await orchestrator.start_task(task.id)

        # Simulate APNs returning 410 Gone
        mock_push_service.send_live_activity_update.return_value = {"status": 410}
        mock_push_service.send_live_activity_update.side_effect = None  # clear spec

        # Re-configure to simulate 410 error handling
        # The push service should raise or return 410, and the orchestrator
        # should react by clearing the token
        from app.services.live_activity_push_service import APNsGoneError

        mock_push_service.send_live_activity_update.side_effect = APNsGoneError(
            token=FAKE_LIVE_ACTIVITY_TOKEN,
        )

        await orchestrator.update_progress(
            task_id=task.id,
            step="developer",
            pct=30,
            detail="Running tests...",
        )

        # After 410, the live_activity_push_token should be cleared
        assert task.live_activity_push_token is None

        # DB should be committed with the cleared token
        mock_db_session.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_token_cleanup_does_not_fail_task(
        self,
        orchestrator: TaskOrchestratorService,
        mock_push_service: AsyncMock,
    ) -> None:
        """A 410 Gone from APNs should clean up the token but should NOT
        cause the task itself to fail — the task should continue normally."""

        user_id = _make_user_id()

        task = await orchestrator.create_task(
            user_id=user_id,
            project_id=None,
            prompt="Optimize database queries",
            task_type="feature",
        )
        await orchestrator.register_live_activity_token(
            task_id=task.id,
            token=FAKE_LIVE_ACTIVITY_TOKEN,
        )
        await orchestrator.start_task(task.id)

        from app.services.live_activity_push_service import APNsGoneError

        mock_push_service.send_live_activity_update.side_effect = APNsGoneError(
            token=FAKE_LIVE_ACTIVITY_TOKEN,
        )

        await orchestrator.update_progress(
            task_id=task.id,
            step="developer",
            pct=50,
            detail="Optimizing queries...",
        )

        # Task should still be in a running state, NOT failed
        assert task.status != TaskStatus.FAILED
        assert task.status in (TaskStatus.IMPLEMENTING, TaskStatus.TESTING)
