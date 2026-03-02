"""Sistem metrik toplama - CPU, RAM, disk kullanim bilgileri."""

from __future__ import annotations

import asyncio
from functools import partial

import psutil

from agent.core.protocol import ResourceMetrics


def _collect_metrics() -> ResourceMetrics:
    """Senkron olarak sistem metriklerini toplar.

    psutil cagrilari blocking oldugu icin bu fonksiyon
    asyncio.to_thread ile cagirilmalidir.
    """
    cpu_percent = psutil.cpu_percent(interval=0.1)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage("/")

    return ResourceMetrics(
        cpu_usage_percent=cpu_percent,
        memory_usage_percent=memory.percent,
        disk_usage_percent=disk.percent,
        disk_free_gb=round(disk.free / (1024**3), 1),
    )


async def get_resource_metrics() -> ResourceMetrics:
    """Sistem kaynak metriklerini asenkron olarak toplar.

    psutil blocking cagrilarini thread pool'da calistirir.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, partial(_collect_metrics))
