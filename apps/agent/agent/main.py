"""RafRaf Host Agent - Python asyncio daemon entry point."""

from __future__ import annotations

import asyncio
import contextlib
import signal
from types import FrameType

import structlog

from agent.core.config import AgentConfig
from agent.core.connection import ConnectionManager
from agent.monitoring.resource_monitor import ResourceMonitor

logger = structlog.get_logger()


def _configure_structlog() -> None:
    """structlog yapilandirmasini ayarlar."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(0),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


async def main() -> None:
    """Agent daemon baslatma noktasi."""
    _configure_structlog()

    await logger.ainfo("RafRaf Host Agent baslatiliyor...")

    config = AgentConfig()
    connection = ConnectionManager(config)
    resource_monitor = ResourceMonitor(config)

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

    # Resource monitor'u baglantiya bagla
    async def _send_via_ws(message: str) -> None:
        """WebSocket uzerinden mesaj gonderir."""
        if connection.is_connected and connection._ws is not None:
            await connection._ws.send(message)

    resource_monitor.set_send_callback(_send_via_ws)

    # Baglanti task'ini basla
    connect_task = asyncio.create_task(connection.connect())

    # Resource monitor'u basla
    await resource_monitor.start()

    # Shutdown sinyali bekle
    await shutdown_event.wait()

    await logger.ainfo("Shutdown sinyali alindi")
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
