"""RafRaf Host Agent - Python asyncio daemon entry point."""

from __future__ import annotations

import asyncio
import contextlib
import signal
import sys
from io import TextIOBase
from pathlib import Path
from types import FrameType
from typing import IO

import structlog

from agent.core.config import AgentConfig
from agent.core.connection import ConnectionManager
from agent.core.task_dispatcher import TaskDispatcher
from agent.discovery.sync_manager import ProjectSyncManager
from agent.monitoring.resource_monitor import ResourceMonitor
from agent.runners.base import BaseRunner
from agent.runners.claude_runner import ClaudeRunner
from agent.runners.docker_runner import DockerRunner
from agent.runners.maestro_runner import MaestroRunner
from agent.runners.playwright_runner import PlaywrightRunner
from agent.runners.shell_runner import ShellRunner

logger = structlog.get_logger()


class _TeeFile(TextIOBase):
    """File-like object that writes to multiple targets simultaneously."""

    def __init__(self, *files: IO[str]) -> None:
        self._files = files

    def write(self, data: str) -> int:  # type: ignore[override]
        for f in self._files:
            f.write(data)
            f.flush()
        return len(data)

    def flush(self) -> None:
        for f in self._files:
            f.flush()


def _configure_structlog() -> None:
    """structlog yapilandirmasini ayarlar."""
    # Log dosyasi olustur
    log_dir = Path(__file__).resolve().parent.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = (log_dir / "agent.log").open("a")  # noqa: SIM115

    tee = _TeeFile(sys.stdout, log_file)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(0),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=tee),
        cache_logger_on_first_use=True,
    )


async def main() -> None:
    """Agent daemon baslatma noktasi."""
    _configure_structlog()

    await logger.ainfo("RafRaf Host Agent baslatiliyor...")

    config = AgentConfig()
    connection = ConnectionManager(config)
    resource_monitor = ResourceMonitor(config)
    project_sync = ProjectSyncManager(config)

    # Signal handler'lar
    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()

    def _signal_handler(_sig: int, _frame: FrameType | None = None) -> None:
        """SIGTERM/SIGINT sinyallerini yakalar."""
        loop.call_soon_threadsafe(shutdown_event.set)

    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    await logger.ainfo(
        "Agent konfigurasyonu yuklendi",
        host_id=config.host_id,
        capabilities=config.get_capabilities(),
    )

    # Runner'lari capability flag'lerine gore olustur
    runners: dict[str, BaseRunner] = {}
    if config.capability_shell:
        runners["shell"] = ShellRunner()
    if config.capability_docker:
        runners["docker"] = DockerRunner(projects={})
    if config.capability_playwright:
        runners["playwright"] = PlaywrightRunner()
    if config.capability_maestro_ios or config.capability_maestro_android:
        runners["maestro"] = MaestroRunner()

    await logger.ainfo(
        "Runner'lar olusturuldu",
        runners=list(runners.keys()),
    )

    # WebSocket send callback
    async def _send_via_ws(message: str) -> None:
        """WebSocket uzerinden mesaj gonderir."""
        await connection.send_message(message)

    # Claude runner olustur (capability flag'ine gore)
    if config.capability_claude_code:
        claude_runner = ClaudeRunner(
            send_callback=_send_via_ws,
            host_id=config.host_id,
            config=config,
        )
        connection.set_claude_runner(claude_runner)
        await logger.ainfo("Claude runner olusturuldu")

    # Task dispatcher'i olustur ve connection'a bagla
    dispatcher = TaskDispatcher(
        runners=runners,
        send_callback=_send_via_ws,
        host_id=config.host_id,
    )
    connection.set_task_handler(dispatcher.dispatch)

    resource_monitor.set_send_callback(_send_via_ws)
    project_sync.set_send_callback(_send_via_ws)

    # Baglanti task'ini basla
    connect_task = asyncio.create_task(connection.connect())

    # Resource monitor ve project sync basla
    await resource_monitor.start()
    await project_sync.start()

    # Shutdown sinyali bekle
    await shutdown_event.wait()

    await logger.ainfo(
        "Shutdown sinyali alindi",
        active_tasks=connection._active_tasks,
    )
    await project_sync.stop()
    await resource_monitor.stop()
    await connection.shutdown()

    # Connect task'i iptal et
    if not connect_task.done():
        connect_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await connect_task

    await logger.ainfo("RafRaf Host Agent durduruldu")


if __name__ == "__main__":
    asyncio.run(main())
