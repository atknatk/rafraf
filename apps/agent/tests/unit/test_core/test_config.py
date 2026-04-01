"""Unit tests for agent configuration."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent.core.config import AgentConfig


class TestAgentConfig:
    """AgentConfig pydantic settings testleri."""

    def test_create_with_required_fields(self) -> None:
        """Zorunlu alanlar ile config olusturulabilir."""
        config = AgentConfig(
            host_id="macbook-pro",
            api_key="test-key",
            backend_ws_url="wss://example.com/ws",
        )
        assert config.host_id == "macbook-pro"
        assert config.api_key == "test-key"
        assert config.backend_ws_url == "wss://example.com/ws"

    def test_default_values(self) -> None:
        """Varsayilan degerler dogru ayarlanir."""
        config = AgentConfig(
            host_id="test",
            api_key="key",
            backend_ws_url="wss://example.com",
        )
        assert config.heartbeat_interval == 30
        assert config.reconnect_initial_delay == 1.0
        assert config.reconnect_max_delay == 60.0
        assert config.version == "0.4.0"

    def test_default_capabilities(self) -> None:
        """Varsayilan yetenekler dogru ayarlanir."""
        config = AgentConfig(
            host_id="test",
            api_key="key",
            backend_ws_url="wss://example.com",
        )
        assert config.capability_docker is False
        assert config.capability_shell is True
        assert config.capability_git is True
        assert config.capability_python is True
        assert config.capability_playwright is False
        assert config.capability_maestro_ios is False
        assert config.capability_maestro_android is False
        assert config.capability_xcode_build is False
        assert config.capability_android_build is False
        assert config.capability_nodejs is False
        assert config.capability_claude_code is True

    def test_heartbeat_interval_minimum(self) -> None:
        """Heartbeat interval minimum deger kontrolu."""
        with pytest.raises(ValidationError):
            AgentConfig(
                host_id="test",
                api_key="key",
                backend_ws_url="wss://example.com",
                heartbeat_interval=2,
            )

    def test_heartbeat_interval_maximum(self) -> None:
        """Heartbeat interval maksimum deger kontrolu."""
        with pytest.raises(ValidationError):
            AgentConfig(
                host_id="test",
                api_key="key",
                backend_ws_url="wss://example.com",
                heartbeat_interval=500,
            )

    def test_reconnect_initial_delay_minimum(self) -> None:
        """Reconnect initial delay minimum kontrolu."""
        with pytest.raises(ValidationError):
            AgentConfig(
                host_id="test",
                api_key="key",
                backend_ws_url="wss://example.com",
                reconnect_initial_delay=0.01,
            )

    def test_reconnect_max_delay_minimum(self) -> None:
        """Reconnect max delay minimum kontrolu."""
        with pytest.raises(ValidationError):
            AgentConfig(
                host_id="test",
                api_key="key",
                backend_ws_url="wss://example.com",
                reconnect_max_delay=0.5,
            )


class TestAgentConfigCapabilities:
    """AgentConfig.get_capabilities() testleri."""

    def test_get_capabilities_default(self) -> None:
        """Varsayilan yetenekler: shell, git, python."""
        config = AgentConfig(
            host_id="test",
            api_key="key",
            backend_ws_url="wss://example.com",
        )
        caps = config.get_capabilities()
        assert "shell" in caps
        assert "git" in caps
        assert "python" in caps
        assert "docker" not in caps

    def test_get_capabilities_all_enabled(self) -> None:
        """Tum yetenekler aktif oldugunda hepsi listede bulunur."""
        config = AgentConfig(
            host_id="test",
            api_key="key",
            backend_ws_url="wss://example.com",
            capability_docker=True,
            capability_playwright=True,
            capability_maestro_ios=True,
            capability_maestro_android=True,
            capability_shell=True,
            capability_xcode_build=True,
            capability_android_build=True,
            capability_git=True,
            capability_python=True,
            capability_nodejs=True,
            capability_claude_code=True,
        )
        caps = config.get_capabilities()
        assert len(caps) == 11
        assert "docker" in caps
        assert "playwright" in caps
        assert "maestro_ios" in caps
        assert "maestro_android" in caps

    def test_get_capabilities_none_enabled(self) -> None:
        """Hicbir yetenek aktif degilse bos liste doner."""
        config = AgentConfig(
            host_id="test",
            api_key="key",
            backend_ws_url="wss://example.com",
            capability_docker=False,
            capability_playwright=False,
            capability_shell=False,
            capability_git=False,
            capability_python=False,
            capability_nodejs=False,
            capability_claude_code=False,
        )
        caps = config.get_capabilities()
        assert caps == []

    def test_get_capabilities_returns_list_of_strings(self) -> None:
        """get_capabilities string listesi dondurur."""
        config = AgentConfig(
            host_id="test",
            api_key="key",
            backend_ws_url="wss://example.com",
        )
        caps = config.get_capabilities()
        assert isinstance(caps, list)
        for cap in caps:
            assert isinstance(cap, str)
