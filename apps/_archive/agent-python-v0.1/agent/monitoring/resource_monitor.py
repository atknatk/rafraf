"""Resource monitor - periyodik CPU, RAM, disk izleme ve esik alarmlari."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

import structlog

from agent.core.protocol import (
    AlarmLevel,
    ResourceAlarm,
    ResourceMetrics,
    build_resource_alarm_message,
    build_resource_report_message,
)
from agent.monitoring.metrics import get_resource_metrics

if TYPE_CHECKING:
    from agent.core.config import AgentConfig

logger = structlog.get_logger()

# Async callback type for sending messages to backend
SendCallbackType = Callable[[str], Awaitable[None]]


class ResourceMonitor:
    """Sistem kaynaklarini periyodik izler ve esik asiminda alarm uretir.

    60 saniye aralikla CPU, RAM, disk metriklerini toplar,
    backend'e JSON formatinda raporlar ve esik degerlerini
    kontrol ederek alarm mesajlari olusturur.
    """

    def __init__(self, config: AgentConfig) -> None:
        self._config = config
        self._report_interval: int = config.resource_report_interval
        self._cpu_threshold: float = config.alarm_cpu_threshold
        self._memory_threshold: float = config.alarm_memory_threshold
        self._disk_threshold: float = config.alarm_disk_threshold
        self._is_running: bool = False
        self._task: asyncio.Task[None] | None = None
        self._last_metrics: ResourceMetrics | None = None
        self._send_callback: SendCallbackType | None = None
        self._active_alarms: set[str] = set()

    @property
    def is_running(self) -> bool:
        """Monitor calisma durumunu dondurur."""
        return self._is_running

    @property
    def last_metrics(self) -> ResourceMetrics | None:
        """Son toplanan metrikleri dondurur."""
        return self._last_metrics

    @property
    def active_alarms(self) -> frozenset[str]:
        """Aktif alarm kaynaklarini dondurur."""
        return frozenset(self._active_alarms)

    def set_send_callback(self, callback: SendCallbackType) -> None:
        """Backend'e mesaj gonderme callback'ini ayarlar.

        Args:
            callback: Async string gonderme fonksiyonu.
        """
        self._send_callback = callback

    async def _send_message(self, message: str) -> None:
        """Callback uzerinden backend'e mesaj gonderir."""
        if self._send_callback is not None:
            try:
                await self._send_callback(message)
            except Exception:
                await logger.aexception("Resource monitor mesaj gonderme hatasi")

    def check_thresholds(self, metrics: ResourceMetrics) -> list[ResourceAlarm]:
        """Metrik degerlerini esik degerleri ile karsilastirir.

        Args:
            metrics: Kontrol edilecek metrikler.

        Returns:
            Esik asiminda olan alarm listesi.
        """
        alarms: list[ResourceAlarm] = []

        if metrics.cpu_usage_percent > self._cpu_threshold:
            alarms.append(
                ResourceAlarm(
                    source="cpu",
                    level=AlarmLevel.CRITICAL
                    if metrics.cpu_usage_percent > 95
                    else AlarmLevel.WARNING,
                    current_value=metrics.cpu_usage_percent,
                    threshold=self._cpu_threshold,
                    message=(
                        f"CPU kullanimi esik degerini asti: "
                        f"{metrics.cpu_usage_percent:.1f}% > {self._cpu_threshold:.1f}%"
                    ),
                ),
            )
            self._active_alarms.add("cpu")
        else:
            self._active_alarms.discard("cpu")

        if metrics.memory_usage_percent > self._memory_threshold:
            alarms.append(
                ResourceAlarm(
                    source="memory",
                    level=AlarmLevel.CRITICAL
                    if metrics.memory_usage_percent > 95
                    else AlarmLevel.WARNING,
                    current_value=metrics.memory_usage_percent,
                    threshold=self._memory_threshold,
                    message=(
                        f"Memory kullanimi esik degerini asti: "
                        f"{metrics.memory_usage_percent:.1f}% > {self._memory_threshold:.1f}%"
                    ),
                ),
            )
            self._active_alarms.add("memory")
        else:
            self._active_alarms.discard("memory")

        if metrics.disk_usage_percent > self._disk_threshold:
            alarms.append(
                ResourceAlarm(
                    source="disk",
                    level=AlarmLevel.CRITICAL
                    if metrics.disk_usage_percent > 95
                    else AlarmLevel.WARNING,
                    current_value=metrics.disk_usage_percent,
                    threshold=self._disk_threshold,
                    message=(
                        f"Disk kullanimi esik degerini asti: "
                        f"{metrics.disk_usage_percent:.1f}% > {self._disk_threshold:.1f}%"
                    ),
                ),
            )
            self._active_alarms.add("disk")
        else:
            self._active_alarms.discard("disk")

        return alarms

    async def collect_and_report(self) -> ResourceMetrics:
        """Metrikleri toplar, backend'e raporlar ve alarmlari kontrol eder.

        Returns:
            Toplanan metrikler.
        """
        metrics = await get_resource_metrics()
        self._last_metrics = metrics

        # Periyodik rapor gonder
        report_message = build_resource_report_message(
            host_id=self._config.host_id,
            metrics=metrics,
        )
        await self._send_message(report_message)

        await logger.ainfo(
            "Resource metrikleri toplandi",
            cpu=metrics.cpu_usage_percent,
            memory=metrics.memory_usage_percent,
            disk=metrics.disk_usage_percent,
            disk_free_gb=metrics.disk_free_gb,
        )

        # Esik kontrolu
        alarms = self.check_thresholds(metrics)
        for alarm in alarms:
            alarm_message = build_resource_alarm_message(
                host_id=self._config.host_id,
                alarm=alarm,
            )
            await self._send_message(alarm_message)

            await logger.awarning(
                "Resource alarm tetiklendi",
                source=alarm.source,
                level=alarm.level.value,
                current_value=alarm.current_value,
                threshold=alarm.threshold,
            )

        return metrics

    async def _monitor_loop(self) -> None:
        """Periyodik izleme dongusu."""
        while self._is_running:
            try:
                await self.collect_and_report()
            except asyncio.CancelledError:
                raise
            except Exception:
                await logger.aexception("Resource monitor dongu hatasi")

            try:
                await asyncio.sleep(self._report_interval)
            except asyncio.CancelledError:
                break

    async def start(self) -> None:
        """Periyodik izlemeyi baslatir."""
        if self._is_running:
            await logger.awarning("Resource monitor zaten calisiyor")
            return

        self._is_running = True
        self._task = asyncio.create_task(self._monitor_loop())
        await logger.ainfo(
            "Resource monitor baslatildi",
            interval=self._report_interval,
            cpu_threshold=self._cpu_threshold,
            memory_threshold=self._memory_threshold,
            disk_threshold=self._disk_threshold,
        )

    async def stop(self) -> None:
        """Periyodik izlemeyi durdurur."""
        if not self._is_running:
            return

        self._is_running = False

        if self._task is not None and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

        self._active_alarms.clear()
        await logger.ainfo("Resource monitor durduruldu")
