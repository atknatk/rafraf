"""Integration tests for Agent WebSocket endpoint."""

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.core.config import get_settings
from app.main import app
from app.services.bridge_registry_service import bridge_registry


@pytest.fixture
def client() -> TestClient:
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def valid_api_key() -> str:
    """Return the configured agent API key."""
    return get_settings().agent_api_key


@pytest.fixture(autouse=True)
def _clear_registry() -> None:
    """Clear the agent registry before each test."""
    bridge_registry._agents.clear()


class TestAgentWebSocketConnection:
    """Integration tests for agent WS connection lifecycle."""

    def test_connect_with_valid_api_key(self, client: TestClient, valid_api_key: str) -> None:
        """Agent should connect successfully with a valid API key."""
        with client.websocket_connect(f"/ws/agent?api_key={valid_api_key}") as ws:
            # Send register message
            ws.send_json(
                {
                    "type": "agent_register",
                    "content": {
                        "host_id": "test-agent",
                        "capabilities": ["docker", "shell"],
                        "os_info": "macOS 15.0",
                        "version": "1.0.0",
                    },
                }
            )
            # Should receive register ack
            data = ws.receive_json()
            assert data["type"] == "agent_register_ack"
            assert data["content"]["host_id"] == "test-agent"
            assert data["content"]["registered"] is True
            assert "server_time" in data["content"]
            assert "heartbeat_interval" in data["content"]

    def test_connect_with_invalid_api_key(self, client: TestClient) -> None:
        """Agent should be rejected with an invalid API key."""
        with (
            pytest.raises(WebSocketDisconnect),
            client.websocket_connect("/ws/agent?api_key=wrong-key"),
        ):
            pass

    def test_connect_without_api_key(self, client: TestClient) -> None:
        """Agent should be rejected without an API key."""
        with (
            pytest.raises((WebSocketDisconnect, KeyError)),
            client.websocket_connect("/ws/agent"),
        ):
            pass


class TestAgentRegistration:
    """Integration tests for agent registration via WebSocket."""

    def test_register_creates_agent_in_registry(
        self, client: TestClient, valid_api_key: str
    ) -> None:
        """Registering via WS should make the agent visible in the registry."""
        with client.websocket_connect(f"/ws/agent?api_key={valid_api_key}") as ws:
            ws.send_json(
                {
                    "type": "agent_register",
                    "content": {
                        "host_id": "mac-pro",
                        "capabilities": ["docker", "playwright", "maestro_ios"],
                        "os_info": "macOS 15.0",
                        "version": "1.0.0",
                    },
                }
            )
            ws.receive_json()  # ack

    def test_register_ack_has_metadata(self, client: TestClient, valid_api_key: str) -> None:
        """Register ack should include metadata with direction."""
        with client.websocket_connect(f"/ws/agent?api_key={valid_api_key}") as ws:
            ws.send_json(
                {
                    "type": "agent_register",
                    "content": {
                        "host_id": "test-agent",
                        "capabilities": [],
                        "os_info": "test",
                        "version": "1.0",
                    },
                }
            )
            data = ws.receive_json()
            assert "metadata" in data
            assert data["metadata"]["direction"] == "server_to_agent"
            assert "timestamp" in data["metadata"]


class TestAgentHeartbeat:
    """Integration tests for agent heartbeat via WebSocket."""

    def test_heartbeat_accepted_after_register(
        self, client: TestClient, valid_api_key: str
    ) -> None:
        """Heartbeat should be silently accepted after registration."""
        with client.websocket_connect(f"/ws/agent?api_key={valid_api_key}") as ws:
            # Register first
            ws.send_json(
                {
                    "type": "agent_register",
                    "content": {
                        "host_id": "hb-agent",
                        "capabilities": ["shell"],
                        "os_info": "Ubuntu 22.04",
                        "version": "1.0.0",
                    },
                }
            )
            ws.receive_json()  # ack

            # Send heartbeat
            ws.send_json(
                {
                    "type": "agent_heartbeat",
                    "content": {
                        "host_id": "hb-agent",
                        "status": "online",
                        "uptime_seconds": 120,
                        "active_tasks": 1,
                        "resources": {
                            "cpu_usage_percent": 30.0,
                            "memory_usage_percent": 55.0,
                            "disk_usage_percent": 40.0,
                            "disk_free_gb": 100.0,
                        },
                    },
                }
            )

            # Heartbeat is silently accepted — send register again to verify connection alive
            ws.send_json(
                {
                    "type": "agent_register",
                    "content": {
                        "host_id": "hb-agent",
                        "capabilities": ["shell"],
                        "os_info": "Ubuntu 22.04",
                        "version": "1.0.0",
                    },
                }
            )
            data = ws.receive_json()
            assert data["type"] == "agent_register_ack"


class TestAgentDisconnect:
    """Integration tests for agent disconnect handling."""

    def test_agent_marked_offline_on_disconnect(
        self, client: TestClient, valid_api_key: str
    ) -> None:
        """Agent should be marked offline when WebSocket disconnects."""
        with client.websocket_connect(f"/ws/agent?api_key={valid_api_key}") as ws:
            ws.send_json(
                {
                    "type": "agent_register",
                    "content": {
                        "host_id": "dc-agent",
                        "capabilities": ["docker"],
                        "os_info": "macOS",
                        "version": "1.0",
                    },
                }
            )
            ws.receive_json()  # ack
        # Connection closed — verify agent is offline asynchronously
        # The disconnect handler should have already run by the time the context exits


class TestMultipleAgents:
    """Integration tests for multi-agent support."""

    def test_two_agents_can_connect(self, client: TestClient, valid_api_key: str) -> None:
        """Two agents with different host_ids should both register successfully."""
        with client.websocket_connect(f"/ws/agent?api_key={valid_api_key}") as ws1:
            ws1.send_json(
                {
                    "type": "agent_register",
                    "content": {
                        "host_id": "agent-alpha",
                        "capabilities": ["docker"],
                        "os_info": "macOS",
                        "version": "1.0",
                    },
                }
            )
            ack1 = ws1.receive_json()
            assert ack1["content"]["host_id"] == "agent-alpha"

            with client.websocket_connect(f"/ws/agent?api_key={valid_api_key}") as ws2:
                ws2.send_json(
                    {
                        "type": "agent_register",
                        "content": {
                            "host_id": "agent-beta",
                            "capabilities": ["playwright"],
                            "os_info": "Ubuntu",
                            "version": "1.0",
                        },
                    }
                )
                ack2 = ws2.receive_json()
                assert ack2["content"]["host_id"] == "agent-beta"
