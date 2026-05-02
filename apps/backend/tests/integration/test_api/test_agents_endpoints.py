"""Integration tests for Agent REST endpoints."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.agent import (
    AgentCapability,
    AgentRegisterPayload,
)
from app.services.bridge_registry_service import bridge_registry


@pytest.fixture
def client() -> TestClient:
    """Create a test client."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_registry() -> None:
    """Clear the agent registry before each test."""
    bridge_registry._agents.clear()


async def _register_agent(
    host_id: str = "macbook-pro",
    capabilities: list[AgentCapability] | None = None,
) -> None:
    """Helper to register an agent directly via the service."""
    payload = AgentRegisterPayload(
        host_id=host_id,
        capabilities=capabilities if capabilities is not None else [AgentCapability.DOCKER],
        os_info="macOS 15.0",
        version="1.0.0",
    )
    await bridge_registry.register_agent(payload, f"conn-{host_id}")


class TestListAgentsEndpoint:
    """Integration tests for GET /api/v1/agents."""

    def test_list_agents_empty(self, client: TestClient) -> None:
        """Listing agents when none are registered should return empty list."""
        response = client.get("/api/v1/agents")
        assert response.status_code == 200
        data = response.json()
        assert data["agents"] == []
        assert data["total"] == 0
        assert data["online_count"] == 0

    async def test_list_agents_returns_registered_agents(self, client: TestClient) -> None:
        """Listing agents should return all registered agents."""
        await _register_agent("agent-1")
        await _register_agent("agent-2")

        response = client.get("/api/v1/agents")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert data["online_count"] == 2
        host_ids = {a["host_id"] for a in data["agents"]}
        assert host_ids == {"agent-1", "agent-2"}

    async def test_list_agents_filter_by_online(self, client: TestClient) -> None:
        """Filtering by status=online should only return online agents."""
        await _register_agent("online-agent")
        await _register_agent("offline-agent")
        await bridge_registry.mark_disconnected("offline-agent")

        response = client.get("/api/v1/agents?status=online")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["agents"][0]["host_id"] == "online-agent"

    async def test_list_agents_filter_by_offline(self, client: TestClient) -> None:
        """Filtering by status=offline should only return offline agents."""
        await _register_agent("agent-1")
        await _register_agent("agent-2")
        await bridge_registry.mark_disconnected("agent-2")

        response = client.get("/api/v1/agents?status=offline")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["agents"][0]["host_id"] == "agent-2"

    def test_list_agents_invalid_status_filter(self, client: TestClient) -> None:
        """Invalid status filter should return 422."""
        response = client.get("/api/v1/agents?status=invalid")
        assert response.status_code == 422

    async def test_list_agents_shows_capabilities(self, client: TestClient) -> None:
        """Agent summary should include capabilities."""
        await _register_agent(
            "cap-agent",
            capabilities=[AgentCapability.DOCKER, AgentCapability.PLAYWRIGHT],
        )
        response = client.get("/api/v1/agents")
        data = response.json()
        agent = data["agents"][0]
        assert "docker" in agent["capabilities"]
        assert "playwright" in agent["capabilities"]


class TestGetAgentEndpoint:
    """Integration tests for GET /api/v1/agents/{host_id}."""

    async def test_get_existing_agent(self, client: TestClient) -> None:
        """Getting a registered agent should return its details."""
        await _register_agent("macbook-pro", [AgentCapability.DOCKER, AgentCapability.SHELL])

        response = client.get("/api/v1/agents/macbook-pro")
        assert response.status_code == 200
        data = response.json()
        assert data["host_id"] == "macbook-pro"
        assert data["status"] == "online"
        assert "docker" in data["capabilities"]
        assert "shell" in data["capabilities"]
        assert "registered_at" in data

    def test_get_nonexistent_agent(self, client: TestClient) -> None:
        """Getting a non-existent agent should return 404."""
        response = client.get("/api/v1/agents/nonexistent")
        assert response.status_code == 404

    async def test_get_agent_status_reflects_disconnect(self, client: TestClient) -> None:
        """Agent detail should reflect offline status after disconnect."""
        await _register_agent("test-dc")
        await bridge_registry.mark_disconnected("test-dc")

        response = client.get("/api/v1/agents/test-dc")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "offline"

    async def test_get_agent_has_os_info(self, client: TestClient) -> None:
        """Agent detail should include os_info from registration."""
        await _register_agent("info-agent")
        response = client.get("/api/v1/agents/info-agent")
        data = response.json()
        assert data["os_info"] == "macOS 15.0"
