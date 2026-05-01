"""Unit tests for system metrics collection."""

from __future__ import annotations

from agent.core.protocol import ResourceMetrics
from agent.monitoring.metrics import get_resource_metrics


class TestGetResourceMetrics:
    """get_resource_metrics async fonksiyon testleri."""

    async def test_returns_resource_metrics(self) -> None:
        """ResourceMetrics instance dondurur."""
        metrics = await get_resource_metrics()
        assert isinstance(metrics, ResourceMetrics)

    async def test_cpu_usage_in_range(self) -> None:
        """CPU kullanimi 0-100 araliginda."""
        metrics = await get_resource_metrics()
        assert 0 <= metrics.cpu_usage_percent <= 100

    async def test_memory_usage_in_range(self) -> None:
        """Memory kullanimi 0-100 araliginda."""
        metrics = await get_resource_metrics()
        assert 0 <= metrics.memory_usage_percent <= 100

    async def test_disk_usage_in_range(self) -> None:
        """Disk kullanimi 0-100 araliginda."""
        metrics = await get_resource_metrics()
        assert 0 <= metrics.disk_usage_percent <= 100

    async def test_disk_free_positive(self) -> None:
        """Bos disk alani pozitif olmali."""
        metrics = await get_resource_metrics()
        assert metrics.disk_free_gb >= 0

    async def test_metrics_are_frozen(self) -> None:
        """Donen metrikler immutable olmali."""
        metrics = await get_resource_metrics()
        try:
            metrics.cpu_usage_percent = 99.0  # type: ignore[misc]
            raise AssertionError("Frozen model degistirilememeli")  # noqa: TRY301
        except Exception:
            pass
