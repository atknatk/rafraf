"""Unit tests for ResourceMonitor - periyodik izleme ve esik alarmlari."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from agent.core.config import AgentConfig
from agent.core.protocol import AlarmLevel, ResourceAlarm, ResourceMetrics
from agent.monitoring.resource_monitor import ResourceMonitor


@pytest.fixture
def monitor_config() -> AgentConfig:
    """Resource monitor test konfigurasyonu."""
    return AgentConfig(
        host_id="test-host",
        api_key="test-api-key-123",
        backend_ws_url="wss://test.example.com/ws/agent",
        heartbeat_interval=5,
        reconnect_initial_delay=0.1,
        reconnect_max_delay=1.0,
        version="0.1.0-test",
        resource_report_interval=10,
        alarm_cpu_threshold=90.0,
        alarm_memory_threshold=85.0,
        alarm_disk_threshold=90.0,
    )


@pytest.fixture
def monitor(monitor_config: AgentConfig) -> ResourceMonitor:
    """ResourceMonitor test instance'i."""
    return ResourceMonitor(monitor_config)


@pytest.fixture
def normal_metrics() -> ResourceMetrics:
    """Normal deger metrikler - esik altinda."""
    return ResourceMetrics(
        cpu_usage_percent=30.0,
        memory_usage_percent=50.0,
        disk_usage_percent=60.0,
        disk_free_gb=200.0,
    )


@pytest.fixture
def warning_metrics() -> ResourceMetrics:
    """Esik ustu metrikler - WARNING seviyesi."""
    return ResourceMetrics(
        cpu_usage_percent=92.0,
        memory_usage_percent=88.0,
        disk_usage_percent=93.0,
        disk_free_gb=15.0,
    )


@pytest.fixture
def critical_metrics() -> ResourceMetrics:
    """Kritik metrikler - CRITICAL seviyesi (>95%)."""
    return ResourceMetrics(
        cpu_usage_percent=97.0,
        memory_usage_percent=96.5,
        disk_usage_percent=98.0,
        disk_free_gb=2.0,
    )


class TestResourceMonitorInit:
    """ResourceMonitor baslangic durumu testleri."""

    def test_initial_state_not_running(self, monitor: ResourceMonitor) -> None:
        """Baslangicta monitor calismamali."""
        assert monitor.is_running is False

    def test_initial_last_metrics_none(self, monitor: ResourceMonitor) -> None:
        """Baslangicta son metrik None olmali."""
        assert monitor.last_metrics is None

    def test_initial_active_alarms_empty(self, monitor: ResourceMonitor) -> None:
        """Baslangicta aktif alarm olmamali."""
        assert monitor.active_alarms == frozenset()

    def test_config_values_applied(self, monitor_config: AgentConfig) -> None:
        """Config degerleri dogru uygulanmali."""
        monitor = ResourceMonitor(monitor_config)
        assert monitor._report_interval == 10
        assert monitor._cpu_threshold == 90.0
        assert monitor._memory_threshold == 85.0
        assert monitor._disk_threshold == 90.0


class TestCheckThresholds:
    """Esik degeri kontrol testleri."""

    def test_no_alarms_below_threshold(
        self,
        monitor: ResourceMonitor,
        normal_metrics: ResourceMetrics,
    ) -> None:
        """Normal degerler icin alarm olmamali."""
        alarms = monitor.check_thresholds(normal_metrics)
        assert len(alarms) == 0

    def test_cpu_warning_alarm(
        self,
        monitor: ResourceMonitor,
        warning_metrics: ResourceMetrics,
    ) -> None:
        """CPU esik ustu WARNING alarm olusturmali."""
        alarms = monitor.check_thresholds(warning_metrics)
        cpu_alarms = [a for a in alarms if a.source == "cpu"]
        assert len(cpu_alarms) == 1
        assert cpu_alarms[0].level == AlarmLevel.WARNING
        assert cpu_alarms[0].current_value == 92.0
        assert cpu_alarms[0].threshold == 90.0

    def test_memory_warning_alarm(
        self,
        monitor: ResourceMonitor,
        warning_metrics: ResourceMetrics,
    ) -> None:
        """Memory esik ustu WARNING alarm olusturmali."""
        alarms = monitor.check_thresholds(warning_metrics)
        memory_alarms = [a for a in alarms if a.source == "memory"]
        assert len(memory_alarms) == 1
        assert memory_alarms[0].level == AlarmLevel.WARNING
        assert memory_alarms[0].current_value == 88.0

    def test_disk_warning_alarm(
        self,
        monitor: ResourceMonitor,
        warning_metrics: ResourceMetrics,
    ) -> None:
        """Disk esik ustu WARNING alarm olusturmali."""
        alarms = monitor.check_thresholds(warning_metrics)
        disk_alarms = [a for a in alarms if a.source == "disk"]
        assert len(disk_alarms) == 1
        assert disk_alarms[0].level == AlarmLevel.WARNING
        assert disk_alarms[0].current_value == 93.0

    def test_all_three_alarms_at_once(
        self,
        monitor: ResourceMonitor,
        warning_metrics: ResourceMetrics,
    ) -> None:
        """Uc kaynak da esik ustunde iken 3 alarm olmali."""
        alarms = monitor.check_thresholds(warning_metrics)
        assert len(alarms) == 3
        sources = {a.source for a in alarms}
        assert sources == {"cpu", "memory", "disk"}

    def test_cpu_critical_alarm(
        self,
        monitor: ResourceMonitor,
        critical_metrics: ResourceMetrics,
    ) -> None:
        """CPU >95% iken CRITICAL alarm olusturmali."""
        alarms = monitor.check_thresholds(critical_metrics)
        cpu_alarms = [a for a in alarms if a.source == "cpu"]
        assert len(cpu_alarms) == 1
        assert cpu_alarms[0].level == AlarmLevel.CRITICAL

    def test_memory_critical_alarm(
        self,
        monitor: ResourceMonitor,
        critical_metrics: ResourceMetrics,
    ) -> None:
        """Memory >95% iken CRITICAL alarm olusturmali."""
        alarms = monitor.check_thresholds(critical_metrics)
        memory_alarms = [a for a in alarms if a.source == "memory"]
        assert len(memory_alarms) == 1
        assert memory_alarms[0].level == AlarmLevel.CRITICAL

    def test_disk_critical_alarm(
        self,
        monitor: ResourceMonitor,
        critical_metrics: ResourceMetrics,
    ) -> None:
        """Disk >95% iken CRITICAL alarm olusturmali."""
        alarms = monitor.check_thresholds(critical_metrics)
        disk_alarms = [a for a in alarms if a.source == "disk"]
        assert len(disk_alarms) == 1
        assert disk_alarms[0].level == AlarmLevel.CRITICAL

    def test_alarm_message_contains_values(
        self,
        monitor: ResourceMonitor,
        warning_metrics: ResourceMetrics,
    ) -> None:
        """Alarm mesaji guncel deger ve esik degerini icermeli."""
        alarms = monitor.check_thresholds(warning_metrics)
        cpu_alarm = next(a for a in alarms if a.source == "cpu")
        assert "92.0%" in cpu_alarm.message
        assert "90.0%" in cpu_alarm.message

    def test_active_alarms_updated_on_threshold_exceeded(
        self,
        monitor: ResourceMonitor,
        warning_metrics: ResourceMetrics,
    ) -> None:
        """Esik asildiginda active_alarms guncellenmeli."""
        monitor.check_thresholds(warning_metrics)
        assert "cpu" in monitor.active_alarms
        assert "memory" in monitor.active_alarms
        assert "disk" in monitor.active_alarms

    def test_active_alarms_cleared_when_below_threshold(
        self,
        monitor: ResourceMonitor,
        warning_metrics: ResourceMetrics,
        normal_metrics: ResourceMetrics,
    ) -> None:
        """Degerler esik altina dustugunde active_alarms temizlenmeli."""
        monitor.check_thresholds(warning_metrics)
        assert len(monitor.active_alarms) == 3

        monitor.check_thresholds(normal_metrics)
        assert len(monitor.active_alarms) == 0

    def test_partial_alarm_only_cpu(self, monitor: ResourceMonitor) -> None:
        """Sadece CPU esik ustu oldugunda tek alarm olmali."""
        metrics = ResourceMetrics(
            cpu_usage_percent=91.0,
            memory_usage_percent=50.0,
            disk_usage_percent=60.0,
            disk_free_gb=200.0,
        )
        alarms = monitor.check_thresholds(metrics)
        assert len(alarms) == 1
        assert alarms[0].source == "cpu"

    def test_exact_threshold_no_alarm(self, monitor: ResourceMonitor) -> None:
        """Esik degerine tam esit deger alarm olusturmamali."""
        metrics = ResourceMetrics(
            cpu_usage_percent=90.0,
            memory_usage_percent=85.0,
            disk_usage_percent=90.0,
            disk_free_gb=20.0,
        )
        alarms = monitor.check_thresholds(metrics)
        assert len(alarms) == 0

    def test_just_above_threshold_triggers_alarm(self, monitor: ResourceMonitor) -> None:
        """Esik degerinin hemen ustu alarm tetiklemeli."""
        metrics = ResourceMetrics(
            cpu_usage_percent=90.1,
            memory_usage_percent=85.1,
            disk_usage_percent=90.1,
            disk_free_gb=20.0,
        )
        alarms = monitor.check_thresholds(metrics)
        assert len(alarms) == 3


class TestSendCallback:
    """Send callback testleri."""

    def test_set_send_callback(self, monitor: ResourceMonitor) -> None:
        """Callback ayarlanabilmeli."""
        callback = AsyncMock()
        monitor.set_send_callback(callback)
        assert monitor._send_callback is callback

    async def test_send_message_calls_callback(self, monitor: ResourceMonitor) -> None:
        """Mesaj gonderme callback'i cagirmali."""
        callback = AsyncMock()
        monitor.set_send_callback(callback)
        await monitor._send_message("test message")
        callback.assert_awaited_once_with("test message")

    async def test_send_message_no_callback_no_error(
        self,
        monitor: ResourceMonitor,
    ) -> None:
        """Callback yokken mesaj gonderme hata vermemeli."""
        await monitor._send_message("test message")

    async def test_send_message_callback_error_handled(
        self,
        monitor: ResourceMonitor,
    ) -> None:
        """Callback hatasi yakalanmali, exception firlatmamali."""
        callback = AsyncMock(side_effect=ConnectionError("connection lost"))
        monitor.set_send_callback(callback)
        # Should not raise
        await monitor._send_message("test message")


class TestCollectAndReport:
    """collect_and_report testleri."""

    async def test_collects_metrics(self, monitor: ResourceMonitor) -> None:
        """Metrikler toplanmali ve saklanmali."""
        metrics = await monitor.collect_and_report()
        assert isinstance(metrics, ResourceMetrics)
        assert monitor.last_metrics is metrics

    async def test_sends_report_message(self, monitor: ResourceMonitor) -> None:
        """Rapor mesaji callback uzerinden gonderilmeli."""
        callback = AsyncMock()
        monitor.set_send_callback(callback)
        await monitor.collect_and_report()
        assert callback.await_count >= 1
        # Ilk cagri report mesaji
        report_msg = callback.call_args_list[0][0][0]
        assert "resource_report" in report_msg

    async def test_sends_alarm_when_threshold_exceeded(
        self,
        monitor: ResourceMonitor,
    ) -> None:
        """Esik asildiginda alarm mesaji gonderilmeli."""
        callback = AsyncMock()
        monitor.set_send_callback(callback)

        high_metrics = ResourceMetrics(
            cpu_usage_percent=95.0,
            memory_usage_percent=50.0,
            disk_usage_percent=50.0,
            disk_free_gb=200.0,
        )

        with patch(
            "agent.monitoring.resource_monitor.get_resource_metrics",
            return_value=high_metrics,
        ):
            await monitor.collect_and_report()

        # 1 report + 1 alarm = 2 calls
        assert callback.await_count == 2
        alarm_msg = callback.call_args_list[1][0][0]
        assert "resource_alarm" in alarm_msg

    async def test_no_alarm_when_below_threshold(
        self,
        monitor: ResourceMonitor,
        normal_metrics: ResourceMetrics,
    ) -> None:
        """Normal degerler icin alarm gonderilmemeli."""
        callback = AsyncMock()
        monitor.set_send_callback(callback)

        with patch(
            "agent.monitoring.resource_monitor.get_resource_metrics",
            return_value=normal_metrics,
        ):
            await monitor.collect_and_report()

        # Sadece 1 report mesaji
        assert callback.await_count == 1


class TestStartStop:
    """Monitor start/stop lifecycle testleri."""

    async def test_start_sets_running(self, monitor: ResourceMonitor) -> None:
        """start() cagrildiktan sonra is_running True olmali."""
        with patch(
            "agent.monitoring.resource_monitor.get_resource_metrics",
            new_callable=AsyncMock,
            return_value=ResourceMetrics(
                cpu_usage_percent=10.0,
                memory_usage_percent=20.0,
                disk_usage_percent=30.0,
                disk_free_gb=500.0,
            ),
        ):
            await monitor.start()
            assert monitor.is_running is True
            await monitor.stop()

    async def test_stop_sets_not_running(self, monitor: ResourceMonitor) -> None:
        """stop() cagrildiktan sonra is_running False olmali."""
        with patch(
            "agent.monitoring.resource_monitor.get_resource_metrics",
            new_callable=AsyncMock,
            return_value=ResourceMetrics(
                cpu_usage_percent=10.0,
                memory_usage_percent=20.0,
                disk_usage_percent=30.0,
                disk_free_gb=500.0,
            ),
        ):
            await monitor.start()
            await monitor.stop()
            assert monitor.is_running is False

    async def test_stop_clears_active_alarms(self, monitor: ResourceMonitor) -> None:
        """stop() aktif alarmlari temizlemeli."""
        warning_metrics = ResourceMetrics(
            cpu_usage_percent=95.0,
            memory_usage_percent=90.0,
            disk_usage_percent=95.0,
            disk_free_gb=5.0,
        )
        with patch(
            "agent.monitoring.resource_monitor.get_resource_metrics",
            new_callable=AsyncMock,
            return_value=warning_metrics,
        ):
            await monitor.start()
            # Let it run once to trigger alarms
            await asyncio.sleep(0.1)
            await monitor.stop()
            assert len(monitor.active_alarms) == 0

    async def test_double_start_ignored(self, monitor: ResourceMonitor) -> None:
        """Zaten calisan monitor'u tekrar baslatma yok sayilmali."""
        with patch(
            "agent.monitoring.resource_monitor.get_resource_metrics",
            new_callable=AsyncMock,
            return_value=ResourceMetrics(
                cpu_usage_percent=10.0,
                memory_usage_percent=20.0,
                disk_usage_percent=30.0,
                disk_free_gb=500.0,
            ),
        ):
            await monitor.start()
            first_task = monitor._task
            await monitor.start()  # ikinci cagri
            assert monitor._task is first_task
            await monitor.stop()

    async def test_stop_without_start_no_error(self, monitor: ResourceMonitor) -> None:
        """Baslatilmamis monitor'u durdurma hata vermemeli."""
        await monitor.stop()
        assert monitor.is_running is False

    async def test_monitor_loop_runs_periodically(self) -> None:
        """Monitor dongusu periyodik calisir."""
        config = AgentConfig(
            host_id="test-host",
            api_key="test-api-key-123",
            backend_ws_url="wss://test.example.com/ws/agent",
            resource_report_interval=10,  # minimum 10
        )
        mon = ResourceMonitor(config)
        call_count = 0

        async def _mock_collect_and_report() -> ResourceMetrics:
            nonlocal call_count
            call_count += 1
            return ResourceMetrics(
                cpu_usage_percent=10.0,
                memory_usage_percent=20.0,
                disk_usage_percent=30.0,
                disk_free_gb=500.0,
            )

        with patch.object(mon, "collect_and_report", side_effect=_mock_collect_and_report):
            await mon.start()
            await asyncio.sleep(0.05)
            await mon.stop()

        assert call_count >= 1


class TestProtocolModels:
    """AlarmLevel ve ResourceAlarm model testleri."""

    def test_alarm_level_warning_value(self) -> None:
        """WARNING seviyesi 'warning' degerine sahip olmali."""
        assert AlarmLevel.WARNING.value == "warning"

    def test_alarm_level_critical_value(self) -> None:
        """CRITICAL seviyesi 'critical' degerine sahip olmali."""
        assert AlarmLevel.CRITICAL.value == "critical"

    def test_resource_alarm_is_frozen(self) -> None:
        """ResourceAlarm frozen olmali."""
        alarm = ResourceAlarm(
            source="cpu",
            level=AlarmLevel.WARNING,
            current_value=92.0,
            threshold=90.0,
            message="test",
        )
        with pytest.raises(ValidationError, match="frozen"):
            alarm.source = "memory"  # type: ignore[misc]

    def test_resource_alarm_fields(self) -> None:
        """ResourceAlarm tum alanlari dogru saklamali."""
        alarm = ResourceAlarm(
            source="disk",
            level=AlarmLevel.CRITICAL,
            current_value=98.0,
            threshold=90.0,
            message="Disk dolu",
        )
        assert alarm.source == "disk"
        assert alarm.level == AlarmLevel.CRITICAL
        assert alarm.current_value == 98.0
        assert alarm.threshold == 90.0
        assert alarm.message == "Disk dolu"


class TestBuildMessages:
    """Mesaj builder fonksiyon testleri."""

    def test_build_resource_report_message_json(self) -> None:
        """resource_report mesaji gecerli JSON olmali."""
        import json

        from agent.core.protocol import build_resource_report_message

        metrics = ResourceMetrics(
            cpu_usage_percent=25.0,
            memory_usage_percent=60.0,
            disk_usage_percent=45.0,
            disk_free_gb=120.0,
        )
        msg_str = build_resource_report_message(host_id="test-host", metrics=metrics)
        data = json.loads(msg_str)
        assert data["type"] == "resource_report"
        assert data["host_id"] == "test-host"
        assert data["content"]["metrics"]["cpu_usage_percent"] == 25.0

    def test_build_resource_alarm_message_json(self) -> None:
        """resource_alarm mesaji gecerli JSON olmali."""
        import json

        from agent.core.protocol import build_resource_alarm_message

        alarm = ResourceAlarm(
            source="cpu",
            level=AlarmLevel.WARNING,
            current_value=92.0,
            threshold=90.0,
            message="CPU yuksek",
        )
        msg_str = build_resource_alarm_message(host_id="test-host", alarm=alarm)
        data = json.loads(msg_str)
        assert data["type"] == "resource_alarm"
        assert data["host_id"] == "test-host"
        assert data["content"]["alarm"]["source"] == "cpu"
        assert data["content"]["alarm"]["level"] == "warning"

    def test_build_resource_report_contains_all_metrics(self) -> None:
        """Rapor mesaji tum metrikleri icermeli."""
        import json

        from agent.core.protocol import build_resource_report_message

        metrics = ResourceMetrics(
            cpu_usage_percent=55.0,
            memory_usage_percent=70.0,
            disk_usage_percent=80.0,
            disk_free_gb=50.0,
        )
        msg_str = build_resource_report_message(host_id="h1", metrics=metrics)
        data = json.loads(msg_str)
        m = data["content"]["metrics"]
        assert m["cpu_usage_percent"] == 55.0
        assert m["memory_usage_percent"] == 70.0
        assert m["disk_usage_percent"] == 80.0
        assert m["disk_free_gb"] == 50.0


class TestConfigMonitorFields:
    """AgentConfig resource monitor alanlari testleri."""

    def test_default_report_interval(self) -> None:
        """Varsayilan raporlama araligi 60 saniye olmali."""
        config = AgentConfig(
            host_id="test",
            api_key="key",
            backend_ws_url="wss://test",
        )
        assert config.resource_report_interval == 60

    def test_default_cpu_threshold(self) -> None:
        """Varsayilan CPU esigi 90% olmali."""
        config = AgentConfig(
            host_id="test",
            api_key="key",
            backend_ws_url="wss://test",
        )
        assert config.alarm_cpu_threshold == 90.0

    def test_default_memory_threshold(self) -> None:
        """Varsayilan memory esigi 85% olmali."""
        config = AgentConfig(
            host_id="test",
            api_key="key",
            backend_ws_url="wss://test",
        )
        assert config.alarm_memory_threshold == 85.0

    def test_default_disk_threshold(self) -> None:
        """Varsayilan disk esigi 90% olmali."""
        config = AgentConfig(
            host_id="test",
            api_key="key",
            backend_ws_url="wss://test",
        )
        assert config.alarm_disk_threshold == 90.0

    def test_custom_thresholds(self) -> None:
        """Ozel esik degerleri ayarlanabilmeli."""
        config = AgentConfig(
            host_id="test",
            api_key="key",
            backend_ws_url="wss://test",
            alarm_cpu_threshold=80.0,
            alarm_memory_threshold=75.0,
            alarm_disk_threshold=85.0,
        )
        assert config.alarm_cpu_threshold == 80.0
        assert config.alarm_memory_threshold == 75.0
        assert config.alarm_disk_threshold == 85.0
