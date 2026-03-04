"""Task Dispatcher - routes task_execute messages to the correct runner."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

import structlog

from agent.core.protocol import (
    build_task_error_message,
    build_task_result_message,
    parse_task_execute,
)

if TYPE_CHECKING:
    from agent.runners.base import BaseRunner

logger = structlog.get_logger()

# Callback type for sending messages back via WebSocket
SendCallback = Callable[[str], Awaitable[None]]


class TaskDispatcher:
    """Routes incoming task_execute messages to the appropriate runner.

    Args:
        runners: Mapping of runner name to runner instance.
        send_callback: Async function to send messages via WebSocket.
        host_id: This agent's host_id for result messages.
    """

    def __init__(
        self,
        runners: dict[str, BaseRunner],
        send_callback: SendCallback,
        host_id: str,
    ) -> None:
        self._runners = runners
        self._send = send_callback
        self._host_id = host_id

    async def dispatch(self, data: dict[str, Any]) -> None:
        """Parse a task_execute message and run it on the correct runner.

        Sends task_result or task_error back via the send_callback.
        """
        task_id = ""
        try:
            content = parse_task_execute(data)
            task_id = content.task_id

            await logger.ainfo(
                "Task calistiriliyor",
                task_id=task_id,
                runner=content.runner,
                action=content.action,
            )

            runner = self._runners.get(content.runner)
            if runner is None:
                available = list(self._runners.keys())
                error_msg = (
                    f"Runner '{content.runner}' bulunamadi. "
                    f"Mevcut runner'lar: {available}"
                )
                await self._send(build_task_error_message(
                    task_id=task_id,
                    host_id=self._host_id,
                    error=error_msg,
                ))
                return

            result = await runner.run(content.action, dict(content.params))

            success = bool(result.get("success", False))
            execution_time_ms = int(result.get("execution_time_ms", 0))

            # Serialize result to a compact string for output
            output = json.dumps(result, ensure_ascii=False, default=str)

            await self._send(build_task_result_message(
                task_id=task_id,
                host_id=self._host_id,
                success=success,
                output=output,
                execution_time_ms=execution_time_ms,
            ))

            await logger.ainfo(
                "Task tamamlandi",
                task_id=task_id,
                runner=content.runner,
                action=content.action,
                success=success,
                elapsed_ms=execution_time_ms,
            )

        except ValueError as exc:
            await logger.awarning("Task parse hatasi", error=str(exc))
            if task_id:
                await self._send(build_task_error_message(
                    task_id=task_id,
                    host_id=self._host_id,
                    error=f"Parse hatasi: {exc}",
                ))

        except Exception as exc:
            await logger.aexception("Task calistirma hatasi", task_id=task_id)
            if task_id:
                await self._send(build_task_error_message(
                    task_id=task_id,
                    host_id=self._host_id,
                    error=f"Calistirma hatasi: {exc}",
                ))
