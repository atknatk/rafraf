"""Task Manager - dispatches tasks to host agents and tracks results.

Manages pending tasks using asyncio.Future for request-response
correlation over WebSocket.
"""

import asyncio
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4

import structlog

from app.core.websocket import ConnectionManager
from app.schemas.agent import AgentTaskSummary, TaskStatus
from app.services.bridge_registry_service import BridgeRegistryService

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

# Default timeouts per runner type (seconds)
_RUNNER_TIMEOUTS: dict[str, int] = {
    "shell": 60,
    "docker": 300,
    "playwright": 120,
    "maestro": 600,
}

# Max task history per agent
_MAX_HISTORY = 100


@dataclass
class _TaskRecord:
    """Internal task record with full lifecycle tracking."""

    task_id: str
    host_id: str
    runner: str
    action: str
    project_id: str | None
    status: TaskStatus
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None
    future: "asyncio.Future[dict[str, object]] | None" = field(default=None, repr=False)

    def to_summary(self) -> AgentTaskSummary:
        duration_ms: int | None = None
        if self.started_at and self.completed_at:
            delta = (self.completed_at - self.started_at).total_seconds()
            duration_ms = int(delta * 1000)
        return AgentTaskSummary(
            task_id=self.task_id,
            host_id=self.host_id,
            runner=self.runner,
            action=self.action,
            status=self.status,
            project_id=self.project_id,
            created_at=self.created_at.isoformat(),
            started_at=self.started_at.isoformat() if self.started_at else None,
            completed_at=self.completed_at.isoformat() if self.completed_at else None,
            duration_ms=duration_ms,
            error=self.error,
        )


class TaskManager:
    """Manages task dispatch to host agents and result tracking.

    Uses asyncio.Future for correlating task_execute requests
    with task_result responses from agents.
    """

    def __init__(
        self,
        agent_registry: BridgeRegistryService,
        agent_manager: ConnectionManager,
    ) -> None:
        self._registry = agent_registry
        self._manager = agent_manager
        self._pending: dict[str, asyncio.Future[dict[str, object]]] = {}
        # Per-agent task history: host_id -> deque of _TaskRecord (newest first)
        self._history: dict[str, deque[_TaskRecord]] = {}
        # task_id -> _TaskRecord for O(1) lookup
        self._records: dict[str, _TaskRecord] = {}

    async def dispatch(
        self,
        *,
        host_id: str,
        runner: str,
        action: str,
        params: dict[str, object],
        project_id: str | None = None,
    ) -> dict[str, object]:
        """Dispatch a task to a host agent and wait for the result.

        Args:
            host_id: Target agent host_id.
            runner: Runner name (shell, docker, playwright, maestro).
            action: Action name for the runner.
            params: Action parameters.
            project_id: Optional project ID for scoping.

        Returns:
            Task result dictionary from the agent.

        Raises:
            ValueError: Agent not found or offline.
            TimeoutError: Agent did not respond in time.
        """
        connection_id = self._registry.get_connection_id(host_id)
        if connection_id is None:
            msg = f"Agent '{host_id}' bulunamadi veya cevrimdisi"
            raise ValueError(msg)

        task_id = str(uuid4())
        timeout = _RUNNER_TIMEOUTS.get(runner, 120)
        now = datetime.now(tz=UTC)

        # Create and register task record
        record = _TaskRecord(
            task_id=task_id,
            host_id=host_id,
            runner=runner,
            action=action,
            project_id=project_id,
            status=TaskStatus.PENDING,
            created_at=now,
        )
        self._records[task_id] = record
        if host_id not in self._history:
            self._history[host_id] = deque(maxlen=_MAX_HISTORY)
        self._history[host_id].appendleft(record)

        # Build task_execute message
        message: dict[str, object] = {
            "id": str(uuid4()),
            "type": "task_execute",
            "content": {
                "task_id": task_id,
                "runner": runner,
                "action": action,
                "params": params,
            },
            "metadata": {
                "timestamp": now.isoformat(),
                "direction": "server_to_agent",
                **({"project_id": project_id} if project_id else {}),
            },
        }

        # Create future for result correlation
        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, object]] = loop.create_future()
        record.future = future
        self._pending[task_id] = future

        await logger.ainfo(
            "task_dispatched",
            task_id=task_id,
            host_id=host_id,
            runner=runner,
            action=action,
            timeout=timeout,
            project_id=project_id,
        )

        # Send to agent
        sent = await self._manager.send_json(connection_id, message)
        if not sent:
            self._pending.pop(task_id, None)
            record.status = TaskStatus.FAILED
            record.error = "Agent ile baglanti kurulamadi"
            record.completed_at = datetime.now(tz=UTC)
            self._records.pop(task_id, None)
            msg = f"Agent '{host_id}' ile baglanti kurulamadi"
            raise ValueError(msg)

        record.status = TaskStatus.RUNNING
        record.started_at = datetime.now(tz=UTC)

        try:
            result = await asyncio.wait_for(future, timeout=timeout)
            record.status = TaskStatus.COMPLETED
            record.completed_at = datetime.now(tz=UTC)
            self._records.pop(task_id, None)
            return result
        except TimeoutError:
            record.status = TaskStatus.TIMEOUT
            record.error = f"Gorev {timeout}s icinde tamamlanmadi"
            record.completed_at = datetime.now(tz=UTC)
            self._pending.pop(task_id, None)
            self._records.pop(task_id, None)
            await logger.awarning(
                "task_timeout",
                task_id=task_id,
                host_id=host_id,
                runner=runner,
                timeout=timeout,
            )
            raise
        finally:
            self._pending.pop(task_id, None)

    def complete(self, task_id: str, result: dict[str, object]) -> bool:
        """Resolve a pending task with its result."""
        future = self._pending.get(task_id)
        if future is None or future.done():
            return False
        record = self._records.get(task_id)
        if record:
            record.status = TaskStatus.COMPLETED
            record.completed_at = datetime.now(tz=UTC)
        future.set_result(result)
        return True

    def fail(self, task_id: str, error: str) -> bool:
        """Reject a pending task with an error."""
        future = self._pending.get(task_id)
        if future is None or future.done():
            return False
        record = self._records.get(task_id)
        if record:
            record.status = TaskStatus.FAILED
            record.error = error
            record.completed_at = datetime.now(tz=UTC)
        future.set_exception(RuntimeError(error))
        return True

    def cancel(self, task_id: str) -> bool:
        """Cancel a pending or running task.

        Returns:
            True if task was found and cancelled, False otherwise.
        """
        future = self._pending.get(task_id)
        if future is None or future.done():
            return False
        record = self._records.get(task_id)
        if record:
            record.status = TaskStatus.CANCELLED
            record.completed_at = datetime.now(tz=UTC)
        future.cancel()
        self._pending.pop(task_id, None)
        self._records.pop(task_id, None)
        return True

    def list_tasks(self, host_id: str, limit: int = 50) -> list[AgentTaskSummary]:
        """Return recent tasks for an agent (newest first).

        Includes both running tasks (from _pending) and history.
        """
        history = self._history.get(host_id, deque())
        return [r.to_summary() for r in list(history)[:limit]]

    @property
    def pending_count(self) -> int:
        """Return the number of pending tasks."""
        return len(self._pending)
