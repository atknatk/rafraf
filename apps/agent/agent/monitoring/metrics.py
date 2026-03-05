"""Sistem metrik toplama - CPU, RAM, disk kullanim bilgileri."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from functools import partial

import psutil

from agent.core.protocol import ClaudeProcessInfo, ResourceMetrics


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


def _collect_claude_processes() -> list[ClaudeProcessInfo]:
    """Calisan 'claude' process'lerini toplar."""
    processes: list[ClaudeProcessInfo] = []
    for proc in psutil.process_iter(["pid", "name", "cmdline", "create_time", "cpu_percent", "memory_info"]):
        try:
            name = proc.info.get("name") or ""
            cmdline = proc.info.get("cmdline") or []
            if "claude" not in name.lower() and not any("claude" in c.lower() for c in cmdline):
                continue
            create_time = proc.info.get("create_time")
            started_at: str | None = None
            if create_time:
                started_at = datetime.fromtimestamp(create_time, tz=UTC).isoformat()
            memory_info = proc.info.get("memory_info")
            memory_mb = round(memory_info.rss / (1024 * 1024), 1) if memory_info else 0.0
            cpu_percent = proc.info.get("cpu_percent") or 0.0
            cmdline_str = " ".join(cmdline[:6]) if cmdline else name
            processes.append(
                ClaudeProcessInfo(
                    pid=proc.info["pid"],
                    cpu_percent=round(float(cpu_percent), 1),
                    memory_mb=memory_mb,
                    started_at=started_at,
                    cmdline=cmdline_str[:200],
                )
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return processes


async def get_resource_metrics() -> ResourceMetrics:
    """Sistem kaynak metriklerini asenkron olarak toplar.

    psutil blocking cagrilarini thread pool'da calistirir.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, partial(_collect_metrics))


async def get_claude_processes() -> list[ClaudeProcessInfo]:
    """Calisan claude process listesini asenkron olarak toplar."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _collect_claude_processes)
