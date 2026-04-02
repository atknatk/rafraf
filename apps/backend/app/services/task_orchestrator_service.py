"""Task orchestrator service — manages task lifecycle state machine."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import TERMINAL_STATES, VALID_TRANSITIONS, Task, TaskStatus
from app.services.agent_registry_service import AgentRegistryService
from app.services.live_activity_push_service import APNsGoneError, LiveActivityPushService


@runtime_checkable
class TaskWSManager(Protocol):
    """Protocol for WebSocket manager used by TaskOrchestratorService."""

    async def broadcast_to_user(
        self, user_id: str | uuid.UUID, message: dict[str, object]
    ) -> int: ...

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

# Step-to-phase-icon mapping for Live Activity content state
_STEP_ICON: dict[str, str] = {
    # Pipeline steps
    "architect": "doc.text.magnifyingglass",
    "developer": "hammer.fill",
    "tester": "checkmark.shield.fill",
    "reviewer": "eye.fill",
    # Stream-based granular phases (chat tasks)
    "thinking": "brain",
    "analyzing": "magnifyingglass",
    "writing": "pencil.line",
    "tool_calling": "hammer.fill",
    "finalizing": "checkmark.diamond",
}

# Ordered pipeline steps for completed_steps counting
_STEP_ORDER: list[str] = ["architect", "developer", "tester", "reviewer"]

# Step name to TaskStatus mapping
_STEP_TO_STATUS: dict[str, TaskStatus] = {
    "architect": TaskStatus.PLANNING,
    "developer": TaskStatus.IMPLEMENTING,
    "tester": TaskStatus.TESTING,
    "reviewer": TaskStatus.REVIEWING,
}

# Heartbeat timeout threshold in seconds
_HEARTBEAT_TIMEOUT_SECONDS: int = 90


class TaskOrchestratorService:
    """Manages the full task lifecycle: creation, transitions, progress, completion."""

    def __init__(
        self,
        db: AsyncSession,
        agent_registry: AgentRegistryService | None = None,
        push_service: LiveActivityPushService | None = None,
        ws_manager: TaskWSManager | None = None,
    ) -> None:
        self._db = db
        self._agent_registry = agent_registry
        self._push_service = push_service or LiveActivityPushService()
        self._ws_manager = ws_manager
        # In-memory task store keyed by task.id for fast lookup
        self._tasks: dict[uuid.UUID, Task] = {}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_task_local(self, task_id: uuid.UUID) -> Task:
        """Retrieve a task from in-memory store. Raises ValueError if not found."""
        task = self._tasks.get(task_id)
        if task is None:
            msg = f"Task {task_id} not found"
            raise ValueError(msg)
        return task

    def _validate_transition(self, current: TaskStatus, target: TaskStatus) -> None:
        """Validate a state transition. Raises ValueError on invalid transition."""
        allowed = VALID_TRANSITIONS.get(current, set())
        if target not in allowed:
            msg = f"Invalid transition from {current.value} to {target.value}"
            raise ValueError(msg)

    async def _broadcast_task_status(
        self,
        task: Task,
        detail: str = "",
    ) -> None:
        """Broadcast task status update via WebSocket to the owning user."""
        if self._ws_manager is None:
            logger.warning("task_status_broadcast_skipped_no_ws_manager", task_id=str(task.id))
            return

        message: dict[str, object] = {
            "type": "task_status",
            "content": {
                "task_id": str(task.id),
                "status": task.status,
                "current_step": task.current_step,
                "progress_pct": task.progress_pct,
                "detail": detail,
                "completed_steps": task.completed_steps,
                "total_steps": task.total_steps,
            },
        }

        sent = await self._ws_manager.broadcast_to_user(task.user_id, message)
        logger.info(
            "task_status_broadcast",
            task_id=str(task.id),
            user_id=str(task.user_id),
            status=task.status,
            sent_to=sent,
        )

    async def _send_live_activity_update_push(
        self,
        task: Task,
        step: str,
        pct: int,
        _detail: str,
    ) -> None:
        """Send a Live Activity update push for a task if it has a push token."""
        token: str | None = getattr(task, "live_activity_push_token", None)
        if not token:
            return

        content_state: dict[str, object] = {
            "status": task.status if isinstance(task.status, str) else task.status,
            "currentStep": step,
            "current_step": step,
            "progress": round(pct / 100.0, 2),
            "progress_pct": pct,
            "completedSteps": int(task.completed_steps),
            "totalSteps": int(task.total_steps),
            "estimatedSecondsRemaining": None,
            "phaseIcon": _STEP_ICON.get(step, "hammer.fill"),
        }

        try:
            await self._push_service.send_live_activity_update(
                token,
                content_state,
                "update",
            )
        except APNsGoneError:
            # Token is invalid — clear it but don't fail the task
            task.live_activity_push_token = None
            await self._db.commit()
            logger.warning(
                "live_activity_token_cleared_410",
                task_id=str(task.id),
                token_prefix=token[:8],
            )
        except Exception:
            # Push failures should not affect task state
            logger.exception(
                "live_activity_push_error",
                task_id=str(task.id),
            )

    async def _send_visible_push(
        self,
        task: Task,
        title: str,
        body: str,
    ) -> None:
        """Send a visible (alert) push notification for task events."""
        try:
            await self._push_service.send_visible_push(
                task.user_id,
                title,
                body,
            )
        except Exception:
            # Push failures should not affect task state
            logger.exception(
                "visible_push_error",
                task_id=str(task.id),
            )

    def _compute_completed_steps(self, current_step: str) -> int:
        """Compute the number of completed steps based on current step."""
        if current_step in _STEP_ORDER:
            return _STEP_ORDER.index(current_step)
        return 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def create_task(
        self,
        user_id: uuid.UUID,
        project_id: uuid.UUID | None,
        prompt: str,
        task_type: str = "feature",
    ) -> Task:
        """Create a new task in QUEUED status."""
        task = Task(
            user_id=user_id,
            project_id=project_id,
            prompt=prompt,
            task_type=task_type,
            title="",
            status=TaskStatus.QUEUED.value,
            current_step=None,
            total_steps=4,
            completed_steps=0,
            progress_pct=0,
            result_summary=None,
            error_message=None,
            claude_session_id=None,
            claude_task_id=None,
            live_activity_push_token=None,
            started_at=None,
            completed_at=None,
        )
        # Ensure task has an id for in-memory tracking
        if task.id is None:
            task.id = uuid.uuid4()
        self._tasks[task.id] = task
        self._db.add(task)
        await self._db.commit()
        logger.info("task_created", task_id=str(task.id), user_id=str(user_id))
        return task

    async def start_task(self, task_id: uuid.UUID) -> Task:
        """Transition task from QUEUED to PLANNING."""
        task = self._get_task_local(task_id)
        current_status = TaskStatus(task.status)
        self._validate_transition(current_status, TaskStatus.PLANNING)

        task.status = TaskStatus.PLANNING.value
        task.started_at = datetime.now(tz=UTC).isoformat()
        task.current_step = "architect"
        await self._db.commit()

        await self._broadcast_task_status(task, detail="Planning started")
        logger.info("task_started", task_id=str(task_id))
        return task

    async def update_progress(
        self,
        task_id: uuid.UUID,
        step: str,
        pct: int,
        detail: str,
    ) -> Task:
        """Update task progress: current step, percentage, and detail."""
        task = self._get_task_local(task_id)

        target_status = _STEP_TO_STATUS.get(step)
        if target_status is not None:
            current_status = TaskStatus(task.status)
            if current_status != target_status:
                allowed = VALID_TRANSITIONS.get(current_status, set())
                if target_status in allowed:
                    task.status = target_status.value

        task.current_step = step
        task.progress_pct = max(0, min(100, pct))
        task.completed_steps = self._compute_completed_steps(step)

        # Send Live Activity push notification (handles APNsGoneError internally)
        await self._send_live_activity_update_push(task, step, pct, detail)

        # Broadcast via WebSocket
        await self._broadcast_task_status(task, detail=detail)

        await self._db.commit()
        logger.info(
            "task_progress_updated",
            task_id=str(task_id),
            step=step,
            pct=task.progress_pct,
            detail=detail,
        )
        return task

    async def complete_task(
        self,
        task_id: uuid.UUID,
        summary: str,
    ) -> Task:
        """Mark task as COMPLETED with result summary."""
        task = self._get_task_local(task_id)
        current_status = TaskStatus(task.status)
        self._validate_transition(current_status, TaskStatus.COMPLETED)

        task.status = TaskStatus.COMPLETED.value
        task.completed_at = datetime.now(tz=UTC).isoformat()
        task.result_summary = summary
        task.progress_pct = 100

        # Send Live Activity end push
        token: str | None = getattr(task, "live_activity_push_token", None)
        if token:
            content_state: dict[str, object] = {
                "status": "completed",
                "currentStep": "Task completed",
                "progress": 1.0,
                "completedSteps": int(task.total_steps),
                "totalSteps": int(task.total_steps),
                "estimatedSecondsRemaining": None,
                "phaseIcon": "checkmark.circle.fill",
            }
            try:
                await self._push_service.send_live_activity_end(
                    push_token=token,
                    content_state=content_state,
                )
            except Exception:
                logger.exception("live_activity_end_push_error", task_id=str(task_id))

        # Send visible push notification
        await self._send_visible_push(
            task=task,
            title=f"Task Completed: {task.title or task.prompt[:50]}",
            body=summary,
        )

        # Broadcast via WebSocket
        await self._broadcast_task_status(task, detail=summary)

        await self._db.commit()
        logger.info("task_completed", task_id=str(task_id))
        return task

    async def fail_task(
        self,
        task_id: uuid.UUID,
        error: str,
    ) -> Task:
        """Mark task as FAILED with error message."""
        task = self._get_task_local(task_id)
        current_status = TaskStatus(task.status)
        self._validate_transition(current_status, TaskStatus.FAILED)

        task.status = TaskStatus.FAILED.value
        task.error_message = error
        task.completed_at = datetime.now(tz=UTC).isoformat()

        # Send Live Activity end push
        token_val: str | None = getattr(task, "live_activity_push_token", None)
        if token_val:
            content_state_fail: dict[str, object] = {
                "status": "failed",
                "currentStep": "Task failed",
                "progress": 0.0,
                "completedSteps": int(task.completed_steps),
                "totalSteps": int(task.total_steps),
                "estimatedSecondsRemaining": None,
                "phaseIcon": "xmark.circle.fill",
            }
            try:
                await self._push_service.send_live_activity_end(
                    push_token=token_val,
                    content_state=content_state_fail,
                )
            except Exception:
                logger.exception("live_activity_end_push_error", task_id=str(task_id))

        # Send visible push notification
        await self._send_visible_push(
            task=task,
            title=f"Task Failed: {task.title or task.prompt[:50]}",
            body=error,
        )

        # Broadcast via WebSocket
        await self._broadcast_task_status(task, detail=error)

        await self._db.commit()
        logger.info("task_failed", task_id=str(task_id), error=error)
        return task

    async def cancel_task(self, task_id: uuid.UUID) -> Task:
        """Cancel an active task. Raises ValueError for terminal tasks."""
        task = self._get_task_local(task_id)
        current_status = TaskStatus(task.status)

        if current_status in TERMINAL_STATES:
            msg = f"Cannot cancel task in {current_status.value} state. Invalid transition."
            raise ValueError(msg)

        self._validate_transition(current_status, TaskStatus.CANCELLED)
        task.status = TaskStatus.CANCELLED.value
        await self._db.commit()
        logger.info("task_cancelled", task_id=str(task_id))
        return task

    async def check_stale_agents(self) -> None:
        """Check for agents whose heartbeat has timed out and fail their active tasks."""
        if self._agent_registry is None:
            return

        # Check all running tasks for stale agents
        for task in list(self._tasks.values()):
            status = TaskStatus(task.status)
            if status in TERMINAL_STATES or status == TaskStatus.QUEUED:
                continue

            # Get agent info for this task
            agent_id = getattr(task, "agent_id", None)
            # For tasks without explicit agent_id, check the default agent
            agent_info = await self._agent_registry.get_agent(agent_id or "default")
            if agent_info is None:
                continue

            last_heartbeat_raw = agent_info.last_heartbeat_at
            if last_heartbeat_raw is None:
                continue

            # Ensure timezone-aware comparison
            now = datetime.now(tz=UTC)
            last_heartbeat = datetime.fromisoformat(last_heartbeat_raw)
            if last_heartbeat.tzinfo is None:
                last_heartbeat = last_heartbeat.replace(tzinfo=UTC)

            elapsed = (now - last_heartbeat).total_seconds()
            if elapsed > _HEARTBEAT_TIMEOUT_SECONDS:
                # Agent is stale — fail the task
                task.status = TaskStatus.FAILED.value
                task.error_message = (
                    f"Agent heartbeat timeout: no heartbeat for {int(elapsed)} seconds. "
                    f"Agent may have disconnected."
                )
                task.completed_at = datetime.now(tz=UTC).isoformat()
                await self._db.commit()
                logger.warning(
                    "task_failed_stale_agent",
                    task_id=str(task.id),
                    elapsed_seconds=elapsed,
                )

    async def get_task(self, task_id: uuid.UUID) -> Task | None:
        """Retrieve a single task by ID from DB, returns None if not found."""
        # Check in-memory cache first (for tasks created in this process)
        cached = self._tasks.get(task_id)
        if cached is not None:
            return cached
        # Fall back to DB query
        result = await self._db.execute(select(Task).where(Task.id == task_id))
        return result.scalar_one_or_none()

    async def get_active_tasks(self, user_id: uuid.UUID) -> list[Task]:
        """Return non-terminal tasks for a user from DB."""
        terminal_values = [s.value for s in TERMINAL_STATES]
        result = await self._db.execute(
            select(Task)
            .where(Task.user_id == user_id)
            .where(Task.status.notin_(terminal_values))
            .order_by(Task.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_task_history(
        self,
        user_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, list[Task] | int]:
        """Return paginated terminal tasks for a user from DB."""
        terminal_values = [s.value for s in TERMINAL_STATES]

        # Count total
        count_result = await self._db.execute(
            select(func.count())
            .select_from(Task)
            .where(Task.user_id == user_id)
            .where(Task.status.in_(terminal_values))
        )
        total: int = count_result.scalar_one()

        # Fetch page
        offset = (page - 1) * page_size
        result = await self._db.execute(
            select(Task)
            .where(Task.user_id == user_id)
            .where(Task.status.in_(terminal_values))
            .order_by(Task.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        tasks = list(result.scalars().all())

        return {
            "tasks": tasks,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def register_live_activity_token(
        self,
        task_id: uuid.UUID,
        token: str,
    ) -> Task:
        """Save an APNs push token on a task for Live Activity updates."""
        task = self._get_task_local(task_id)
        task.live_activity_push_token = token
        await self._db.commit()
        logger.info("live_activity_token_registered", task_id=str(task_id))
        return task
