"""Periyodik proje kesfetme ve backend'e senkronizasyon."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

import structlog

from agent.core.protocol import ProjectSyncEntry, build_project_sync_message
from agent.discovery.project_discovery import ProjectDiscovery

if TYPE_CHECKING:
    from agent.core.config import AgentConfig

logger = structlog.get_logger()

SendCallbackType = Callable[[str], Awaitable[None]]


class ProjectSyncManager:
    """Periyodik proje kesfetme ve backend'e senkronizasyon.

    ResourceMonitor pattern'ini takip eder (start/stop/set_send_callback).
    """

    def __init__(self, config: AgentConfig) -> None:
        self._config = config
        self._discovery = ProjectDiscovery(config)
        self._sync_interval: int = config.project_sync_interval
        self._is_running: bool = False
        self._task: asyncio.Task[None] | None = None
        self._send_callback: SendCallbackType | None = None

    @property
    def is_running(self) -> bool:
        """Sync manager calisma durumunu dondurur."""
        return self._is_running

    def set_send_callback(self, callback: SendCallbackType) -> None:
        """Backend'e mesaj gonderme callback'ini ayarlar."""
        self._send_callback = callback

    async def _send_message(self, message: str) -> None:
        """Callback uzerinden backend'e mesaj gonderir."""
        if self._send_callback is not None:
            try:
                await self._send_callback(message)
            except Exception:
                await logger.aexception("project_sync_send_error")

    async def sync_once(self) -> int:
        """Projeleri kesfi eder ve project_sync mesaji gonderir.

        Returns:
            Kesfedilen proje sayisi.
        """
        discovered = await self._discovery.discover_all()

        if not discovered:
            await logger.ainfo("project_sync_no_projects")
            return 0

        entries = [
            ProjectSyncEntry(
                name=p.name,
                repository_url=p.repository_url,
                local_path=p.local_path,
                tech_stack=p.tech_stack,
                source=p.source,
            )
            for p in discovered
        ]

        message = build_project_sync_message(
            host_id=self._config.host_id,
            projects=entries,
        )
        await self._send_message(message)

        await logger.ainfo("project_sync_sent", count=len(entries))
        return len(entries)

    async def _sync_loop(self) -> None:
        """Periyodik senkronizasyon dongusu."""
        # Ilk sync hemen yap
        try:
            await self.sync_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            await logger.aexception("project_sync_initial_error")

        while self._is_running:
            try:
                await asyncio.sleep(self._sync_interval)
            except asyncio.CancelledError:
                break

            try:
                await self.sync_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                await logger.aexception("project_sync_loop_error")

    async def start(self) -> None:
        """Periyodik proje sync'i baslatir."""
        if self._is_running:
            await logger.awarning("project_sync_already_running")
            return

        self._is_running = True
        self._task = asyncio.create_task(self._sync_loop())
        await logger.ainfo(
            "project_sync_started",
            interval=self._sync_interval,
            scan_paths=self._config.project_scan_paths,
            config_path=self._config.project_config_path,
        )

    async def stop(self) -> None:
        """Periyodik proje sync'i durdurur."""
        if not self._is_running:
            return

        self._is_running = False

        if self._task is not None and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

        await logger.ainfo("project_sync_stopped")
