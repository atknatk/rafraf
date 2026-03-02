"""Unit tests for AgentRegistryService."""

import asyncio

import pytest

from app.schemas.agent import (
    AgentCapability,
    AgentHeartbeatPayload,
    AgentRegisterPayload,
    AgentStatus,
    ResourceInfo,
)
from app.services.agent_registry_service import AgentRegistryService


def _make_register_payload(
    host_id: str = "macbook-pro",
    capabilities: list[AgentCapability] | None = None,
    os_info: str = "macOS 15.0",
    version: str = "1.0.0",
) -> AgentRegisterPayload:
    return AgentRegisterPayload(
        host_id=host_id,
        capabilities=capabilities if capabilities is not None else [AgentCapability.DOCKER],
        os_info=os_info,
        version=version,
    )


def _make_heartbeat_payload(
    host_id: str = "macbook-pro",
    status: AgentStatus = AgentStatus.ONLINE,
    uptime_seconds: int = 3600,
    active_tasks: int = 0,
) -> AgentHeartbeatPayload:
    return AgentHeartbeatPayload(
        host_id=host_id,
        status=status,
        uptime_seconds=uptime_seconds,
        active_tasks=active_tasks,
        resources=ResourceInfo(
            cpu_usage_percent=25.0,
            memory_usage_percent=50.0,
            disk_usage_percent=40.0,
            disk_free_gb=150.0,
        ),
    )


class TestAgentRegistration:
    """Tests for agent registration."""

    async def test_register_new_agent_returns_true(self) -> None:
        service = AgentRegistryService()
        is_new = await service.register_agent(_make_register_payload(), "conn-1")
        assert is_new is True

    async def test_re_register_existing_agent_returns_false(self) -> None:
        service = AgentRegistryService()
        await service.register_agent(_make_register_payload(), "conn-1")
        is_new = await service.register_agent(_make_register_payload(), "conn-2")
        assert is_new is False

    async def test_register_multiple_agents(self) -> None:
        service = AgentRegistryService()
        await service.register_agent(_make_register_payload(host_id="agent-1"), "conn-1")
        await service.register_agent(_make_register_payload(host_id="agent-2"), "conn-2")
        result = await service.list_agents()
        assert result.total == 2

    async def test_registered_agent_is_online(self) -> None:
        service = AgentRegistryService()
        await service.register_agent(_make_register_payload(), "conn-1")
        detail = await service.get_agent("macbook-pro")
        assert detail is not None
        assert detail.status == AgentStatus.ONLINE


class TestAgentHeartbeat:
    """Tests for heartbeat processing."""

    async def test_heartbeat_updates_status(self) -> None:
        service = AgentRegistryService()
        await service.register_agent(_make_register_payload(), "conn-1")
        found = await service.process_heartbeat(
            _make_heartbeat_payload(status=AgentStatus.BUSY)
        )
        assert found is True
        detail = await service.get_agent("macbook-pro")
        assert detail is not None
        assert detail.status == AgentStatus.BUSY

    async def test_heartbeat_updates_resources(self) -> None:
        service = AgentRegistryService()
        await service.register_agent(_make_register_payload(), "conn-1")
        await service.process_heartbeat(_make_heartbeat_payload(uptime_seconds=7200))
        detail = await service.get_agent("macbook-pro")
        assert detail is not None
        assert detail.uptime_seconds == 7200
        assert detail.resources is not None
        assert detail.resources.cpu_usage_percent == 25.0

    async def test_heartbeat_unknown_agent_returns_false(self) -> None:
        service = AgentRegistryService()
        found = await service.process_heartbeat(_make_heartbeat_payload(host_id="unknown"))
        assert found is False

    async def test_heartbeat_updates_active_tasks(self) -> None:
        service = AgentRegistryService()
        await service.register_agent(_make_register_payload(), "conn-1")
        await service.process_heartbeat(_make_heartbeat_payload(active_tasks=5))
        detail = await service.get_agent("macbook-pro")
        assert detail is not None
        assert detail.active_tasks == 5


class TestAgentDisconnection:
    """Tests for agent disconnect handling."""

    async def test_mark_disconnected_sets_offline(self) -> None:
        service = AgentRegistryService()
        await service.register_agent(_make_register_payload(), "conn-1")
        await service.mark_disconnected("macbook-pro")
        detail = await service.get_agent("macbook-pro")
        assert detail is not None
        assert detail.status == AgentStatus.OFFLINE

    async def test_mark_disconnected_unknown_agent_no_error(self) -> None:
        service = AgentRegistryService()
        # Should not raise
        await service.mark_disconnected("nonexistent")

    async def test_unregister_by_connection_returns_host_id(self) -> None:
        service = AgentRegistryService()
        await service.register_agent(_make_register_payload(), "conn-1")
        host_id = await service.unregister_by_connection("conn-1")
        assert host_id == "macbook-pro"

    async def test_unregister_by_connection_sets_offline(self) -> None:
        service = AgentRegistryService()
        await service.register_agent(_make_register_payload(), "conn-1")
        await service.unregister_by_connection("conn-1")
        detail = await service.get_agent("macbook-pro")
        assert detail is not None
        assert detail.status == AgentStatus.OFFLINE

    async def test_unregister_by_unknown_connection_returns_none(self) -> None:
        service = AgentRegistryService()
        result = await service.unregister_by_connection("unknown-conn")
        assert result is None


class TestAgentQueries:
    """Tests for agent query methods."""

    async def test_list_agents_empty(self) -> None:
        service = AgentRegistryService()
        result = await service.list_agents()
        assert result.total == 0
        assert result.online_count == 0
        assert result.agents == []

    async def test_list_agents_filter_by_status(self) -> None:
        service = AgentRegistryService()
        await service.register_agent(_make_register_payload(host_id="agent-1"), "c1")
        await service.register_agent(_make_register_payload(host_id="agent-2"), "c2")
        await service.mark_disconnected("agent-2")

        online_result = await service.list_agents(status_filter=AgentStatus.ONLINE)
        assert online_result.total == 1
        assert online_result.agents[0].host_id == "agent-1"

        offline_result = await service.list_agents(status_filter=AgentStatus.OFFLINE)
        assert offline_result.total == 1
        assert offline_result.agents[0].host_id == "agent-2"

    async def test_list_agents_online_count(self) -> None:
        service = AgentRegistryService()
        await service.register_agent(_make_register_payload(host_id="a1"), "c1")
        await service.register_agent(_make_register_payload(host_id="a2"), "c2")
        await service.register_agent(_make_register_payload(host_id="a3"), "c3")
        await service.mark_disconnected("a3")

        result = await service.list_agents()
        assert result.total == 3
        assert result.online_count == 2

    async def test_get_agent_not_found(self) -> None:
        service = AgentRegistryService()
        result = await service.get_agent("nonexistent")
        assert result is None

    async def test_get_agent_has_capabilities(self) -> None:
        service = AgentRegistryService()
        await service.register_agent(
            _make_register_payload(
                host_id="mac",
                capabilities=[AgentCapability.DOCKER, AgentCapability.MAESTRO_IOS],
            ),
            "c1",
        )
        detail = await service.get_agent("mac")
        assert detail is not None
        assert AgentCapability.DOCKER in detail.capabilities
        assert AgentCapability.MAESTRO_IOS in detail.capabilities

    async def test_get_agent_has_registered_at(self) -> None:
        service = AgentRegistryService()
        await service.register_agent(_make_register_payload(), "c1")
        detail = await service.get_agent("macbook-pro")
        assert detail is not None
        assert detail.registered_at is not None
        assert "T" in detail.registered_at  # ISO format


class TestStaleDetection:
    """Tests for stale agent detection background task."""

    async def test_stale_agent_marked_offline(self) -> None:
        service = AgentRegistryService(
            heartbeat_timeout_seconds=0,  # Immediate timeout
            stale_check_interval_seconds=0,  # Immediate check
        )
        await service.register_agent(_make_register_payload(), "c1")

        # Manually run a single check cycle instead of the loop
        # Simulate by waiting briefly and checking
        await service.start_stale_checker()
        await asyncio.sleep(0.2)  # Give the background task time to detect
        await service.stop_stale_checker()

        detail = await service.get_agent("macbook-pro")
        assert detail is not None
        assert detail.status == AgentStatus.OFFLINE

    async def test_start_stop_stale_checker(self) -> None:
        service = AgentRegistryService(stale_check_interval_seconds=60)
        await service.start_stale_checker()
        assert service._stale_task is not None
        assert not service._stale_task.done()
        await service.stop_stale_checker()
        assert service._stale_task.done()

    async def test_double_start_does_not_duplicate(self) -> None:
        service = AgentRegistryService(stale_check_interval_seconds=60)
        await service.start_stale_checker()
        first_task = service._stale_task
        await service.start_stale_checker()
        assert service._stale_task is first_task
        await service.stop_stale_checker()
