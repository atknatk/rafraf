"""Task Manager - dispatches tasks to host agents and tracks results.

Manages pending tasks using asyncio.Future for request-response
correlation over WebSocket.
"""

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import structlog

from app.core.websocket import ConnectionManager
from app.services.agent_registry_service import AgentRegistryService

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

# Default timeouts per runner type (seconds)
_RUNNER_TIMEOUTS: dict[str, int] = {
    "shell": 60,
    "docker": 300,
    "playwright": 120,
    "maestro": 600,
}


class TaskManager:
    """Manages task dispatch to host agents and result tracking.

    Uses asyncio.Future for correlating task_execute requests
    with task_result responses from agents.
    """

    def __init__(
        self,
        agent_registry: AgentRegistryService,
        agent_manager: ConnectionManager,
    ) -> None:
        self._registry = agent_registry
        self._manager = agent_manager
        self._pending: dict[str, asyncio.Future[dict[str, object]]] = {}

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
                "timestamp": datetime.now(tz=UTC).isoformat(),
                "direction": "server_to_agent",
                **({"project_id": project_id} if project_id else {}),
            },
        }

        # Create future for result correlation
        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, object]] = loop.create_future()
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
            msg = f"Agent '{host_id}' ile baglanti kurulamadi"
            raise ValueError(msg)

        try:
            result = await asyncio.wait_for(future, timeout=timeout)
            return result
        except TimeoutError:
            self._pending.pop(task_id, None)
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
        """Resolve a pending task with its result.

        Args:
            task_id: Task identifier.
            result: Result dictionary from the agent.

        Returns:
            True if task was found and resolved, False otherwise.
        """
        future = self._pending.get(task_id)
        if future is None or future.done():
            return False
        future.set_result(result)
        return True

    def fail(self, task_id: str, error: str) -> bool:
        """Reject a pending task with an error.

        Args:
            task_id: Task identifier.
            error: Error message.

        Returns:
            True if task was found and rejected, False otherwise.
        """
        future = self._pending.get(task_id)
        if future is None or future.done():
            return False
        future.set_exception(RuntimeError(error))
        return True

    @property
    def pending_count(self) -> int:
        """Return the number of pending tasks."""
        return len(self._pending)
