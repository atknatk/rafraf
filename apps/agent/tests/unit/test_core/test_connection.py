"""Unit tests for connection manager."""

from __future__ import annotations

from agent.core.config import AgentConfig
from agent.core.connection import ConnectionManager


class TestConnectionManagerInit:
    """ConnectionManager baslangic durum testleri."""

    def test_initial_state(self, agent_config: AgentConfig) -> None:
        """Baslangic durumunda bagli degil."""
        cm = ConnectionManager(agent_config)
        assert cm.is_connected is False

    def test_uptime_starts_at_zero(self, agent_config: AgentConfig) -> None:
        """Uptime baslangicta 0 civarinda."""
        cm = ConnectionManager(agent_config)
        assert cm.uptime_seconds >= 0
        assert cm.uptime_seconds < 2  # Test baslarken max 2 saniye


class TestExponentialBackoff:
    """Exponential backoff hesaplama testleri."""

    def test_initial_delay(self, agent_config: AgentConfig) -> None:
        """Ilk delay initial_delay degerinde."""
        cm = ConnectionManager(agent_config)
        delay = cm._calculate_backoff()
        assert delay == agent_config.reconnect_initial_delay

    def test_exponential_increase(self, agent_config: AgentConfig) -> None:
        """Her cagri delay'i 2x artirir."""
        cm = ConnectionManager(agent_config)
        delay1 = cm._calculate_backoff()
        delay2 = cm._calculate_backoff()
        delay3 = cm._calculate_backoff()
        assert delay2 == delay1 * 2
        assert delay3 == delay2 * 2

    def test_max_delay_cap(self, agent_config: AgentConfig) -> None:
        """Delay max_delay'i asmaz."""
        cm = ConnectionManager(agent_config)
        # Yeterli sayida cagirim yap
        for _ in range(20):
            delay = cm._calculate_backoff()
        assert delay <= agent_config.reconnect_max_delay

    def test_reset_backoff(self, agent_config: AgentConfig) -> None:
        """Reset sonrasi delay baslangic degerine doner."""
        cm = ConnectionManager(agent_config)
        cm._calculate_backoff()
        cm._calculate_backoff()
        cm._calculate_backoff()
        cm._reset_backoff()
        delay = cm._calculate_backoff()
        assert delay == agent_config.reconnect_initial_delay

    def test_backoff_sequence(self) -> None:
        """Backoff sirasi: 1, 2, 4, 8, 16, 32, 60, 60..."""
        config = AgentConfig(
            host_id="test",
            api_key="key",
            backend_ws_url="wss://example.com",
            reconnect_initial_delay=1.0,
            reconnect_max_delay=60.0,
        )
        cm = ConnectionManager(config)
        expected_delays = [1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 60.0, 60.0]
        for expected in expected_delays:
            actual = cm._calculate_backoff()
            assert actual == expected, f"Expected {expected}, got {actual}"


class TestConnectionManagerOsInfo:
    """OS bilgisi testleri."""

    def test_os_info_not_empty(self, agent_config: AgentConfig) -> None:
        """OS bilgisi bos olmamali."""
        cm = ConnectionManager(agent_config)
        os_info = cm._get_os_info()
        assert len(os_info) > 0

    def test_os_info_contains_system_name(self, agent_config: AgentConfig) -> None:
        """OS bilgisi sistem adini icermeli."""
        cm = ConnectionManager(agent_config)
        os_info = cm._get_os_info()
        # Darwin (macOS) veya Linux olmali
        assert "Darwin" in os_info or "Linux" in os_info or "Windows" in os_info
