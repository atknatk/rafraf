"""Shared test fixtures for agent tests."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from agent.core.config import AgentConfig
from agent.core.protocol import ResourceMetrics


@pytest.fixture
def agent_config() -> AgentConfig:
    """Test icin AgentConfig olusturur."""
    return AgentConfig(
        host_id="test-host",
        api_key="test-api-key-123",
        backend_ws_url="wss://test.example.com/ws/agent",
        heartbeat_interval=5,
        reconnect_initial_delay=0.1,
        reconnect_max_delay=1.0,
        version="0.1.0-test",
        capability_docker=True,
        capability_shell=True,
        capability_git=True,
        capability_python=True,
    )


@pytest.fixture
def sample_resource_metrics() -> ResourceMetrics:
    """Test icin ornek ResourceMetrics olusturur."""
    return ResourceMetrics(
        cpu_usage_percent=25.5,
        memory_usage_percent=60.0,
        disk_usage_percent=45.0,
        disk_free_gb=120.5,
    )


@pytest.fixture
def mock_websocket() -> AsyncMock:
    """Mock WebSocket baglantisi olusturur."""
    ws = AsyncMock()
    ws.send = AsyncMock()
    ws.recv = AsyncMock()
    ws.close = AsyncMock()
    return ws
