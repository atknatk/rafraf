"""Unit tests for agent Pydantic schemas."""

import pytest
from pydantic import ValidationError

from app.schemas.agent import (
    AgentCapability,
    AgentDetailResponse,
    AgentHeartbeatPayload,
    AgentListResponse,
    AgentRegisterAckPayload,
    AgentRegisterPayload,
    AgentStatus,
    AgentSummary,
    ResourceInfo,
)


class TestAgentStatus:
    """Tests for AgentStatus enum."""

    def test_online_value(self) -> None:
        assert AgentStatus.ONLINE == "online"

    def test_offline_value(self) -> None:
        assert AgentStatus.OFFLINE == "offline"

    def test_busy_value(self) -> None:
        assert AgentStatus.BUSY == "busy"


class TestAgentCapability:
    """Tests for AgentCapability enum."""

    def test_docker_capability(self) -> None:
        assert AgentCapability.DOCKER == "docker"

    def test_playwright_capability(self) -> None:
        assert AgentCapability.PLAYWRIGHT == "playwright"

    def test_maestro_ios_capability(self) -> None:
        assert AgentCapability.MAESTRO_IOS == "maestro_ios"

    def test_shell_capability(self) -> None:
        assert AgentCapability.SHELL == "shell"

    def test_all_capabilities_count(self) -> None:
        assert len(AgentCapability) == 11


class TestResourceInfo:
    """Tests for ResourceInfo schema."""

    def test_valid_resource_info(self) -> None:
        info = ResourceInfo(
            cpu_usage_percent=45.2,
            memory_usage_percent=67.8,
            disk_usage_percent=55.0,
            disk_free_gb=120.5,
        )
        assert info.cpu_usage_percent == 45.2
        assert info.memory_usage_percent == 67.8
        assert info.disk_usage_percent == 55.0
        assert info.disk_free_gb == 120.5

    def test_resource_info_is_frozen(self) -> None:
        info = ResourceInfo(
            cpu_usage_percent=10.0,
            memory_usage_percent=20.0,
            disk_usage_percent=30.0,
            disk_free_gb=40.0,
        )
        with pytest.raises(ValidationError):
            info.cpu_usage_percent = 99.0  # type: ignore[misc]

    def test_resource_info_invalid_cpu_negative(self) -> None:
        with pytest.raises(ValidationError):
            ResourceInfo(
                cpu_usage_percent=-1.0,
                memory_usage_percent=20.0,
                disk_usage_percent=30.0,
                disk_free_gb=40.0,
            )

    def test_resource_info_invalid_cpu_over_100(self) -> None:
        with pytest.raises(ValidationError):
            ResourceInfo(
                cpu_usage_percent=101.0,
                memory_usage_percent=20.0,
                disk_usage_percent=30.0,
                disk_free_gb=40.0,
            )

    def test_resource_info_boundary_zero(self) -> None:
        info = ResourceInfo(
            cpu_usage_percent=0.0,
            memory_usage_percent=0.0,
            disk_usage_percent=0.0,
            disk_free_gb=0.0,
        )
        assert info.cpu_usage_percent == 0.0

    def test_resource_info_boundary_max(self) -> None:
        info = ResourceInfo(
            cpu_usage_percent=100.0,
            memory_usage_percent=100.0,
            disk_usage_percent=100.0,
            disk_free_gb=1000.0,
        )
        assert info.cpu_usage_percent == 100.0


class TestAgentRegisterPayload:
    """Tests for AgentRegisterPayload schema."""

    def test_valid_register_payload(self) -> None:
        payload = AgentRegisterPayload(
            host_id="macbook-pro",
            capabilities=[AgentCapability.DOCKER, AgentCapability.SHELL],
            os_info="macOS 15.0",
            version="1.0.0",
        )
        assert payload.host_id == "macbook-pro"
        assert len(payload.capabilities) == 2

    def test_register_payload_is_frozen(self) -> None:
        payload = AgentRegisterPayload(
            host_id="test",
            capabilities=[],
            os_info="test",
            version="1.0",
        )
        with pytest.raises(ValidationError):
            payload.host_id = "changed"  # type: ignore[misc]

    def test_register_payload_empty_host_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AgentRegisterPayload(
                host_id="",
                capabilities=[],
                os_info="macOS",
                version="1.0",
            )

    def test_register_payload_host_id_max_length(self) -> None:
        with pytest.raises(ValidationError):
            AgentRegisterPayload(
                host_id="x" * 101,
                capabilities=[],
                os_info="macOS",
                version="1.0",
            )

    def test_register_payload_empty_capabilities(self) -> None:
        payload = AgentRegisterPayload(
            host_id="test",
            capabilities=[],
            os_info="macOS",
            version="1.0",
        )
        assert payload.capabilities == []


class TestAgentHeartbeatPayload:
    """Tests for AgentHeartbeatPayload schema."""

    def test_valid_heartbeat_payload(self) -> None:
        payload = AgentHeartbeatPayload(
            host_id="macbook-pro",
            status=AgentStatus.ONLINE,
            uptime_seconds=3600,
            active_tasks=2,
            resources=ResourceInfo(
                cpu_usage_percent=30.0,
                memory_usage_percent=50.0,
                disk_usage_percent=60.0,
                disk_free_gb=100.0,
            ),
        )
        assert payload.host_id == "macbook-pro"
        assert payload.status == AgentStatus.ONLINE
        assert payload.uptime_seconds == 3600
        assert payload.active_tasks == 2
        assert payload.resources.cpu_usage_percent == 30.0

    def test_heartbeat_payload_is_frozen(self) -> None:
        payload = AgentHeartbeatPayload(
            host_id="test",
            status=AgentStatus.ONLINE,
            uptime_seconds=0,
            active_tasks=0,
            resources=ResourceInfo(
                cpu_usage_percent=0.0,
                memory_usage_percent=0.0,
                disk_usage_percent=0.0,
                disk_free_gb=0.0,
            ),
        )
        with pytest.raises(ValidationError):
            payload.host_id = "changed"  # type: ignore[misc]

    def test_heartbeat_negative_uptime_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AgentHeartbeatPayload(
                host_id="test",
                status=AgentStatus.ONLINE,
                uptime_seconds=-1,
                active_tasks=0,
                resources=ResourceInfo(
                    cpu_usage_percent=0.0,
                    memory_usage_percent=0.0,
                    disk_usage_percent=0.0,
                    disk_free_gb=0.0,
                ),
            )


class TestAgentRegisterAckPayload:
    """Tests for AgentRegisterAckPayload schema."""

    def test_valid_ack_payload(self) -> None:
        ack = AgentRegisterAckPayload(
            host_id="macbook-pro",
            registered=True,
            server_time="2026-03-02T10:00:00Z",
            heartbeat_interval=30,
        )
        assert ack.host_id == "macbook-pro"
        assert ack.registered is True
        assert ack.heartbeat_interval == 30

    def test_ack_payload_is_frozen(self) -> None:
        ack = AgentRegisterAckPayload(
            host_id="test",
            registered=True,
            server_time="2026-03-02T10:00:00Z",
            heartbeat_interval=30,
        )
        with pytest.raises(ValidationError):
            ack.host_id = "changed"  # type: ignore[misc]


class TestAgentSummary:
    """Tests for AgentSummary response DTO."""

    def test_valid_agent_summary(self) -> None:
        summary = AgentSummary(
            host_id="macbook-pro",
            status=AgentStatus.ONLINE,
            capabilities=[AgentCapability.DOCKER],
        )
        assert summary.host_id == "macbook-pro"
        assert summary.last_heartbeat_at is None
        assert summary.resources is None

    def test_agent_summary_with_all_fields(self) -> None:
        summary = AgentSummary(
            host_id="ubuntu-dev",
            status=AgentStatus.BUSY,
            capabilities=[AgentCapability.DOCKER, AgentCapability.PLAYWRIGHT],
            last_heartbeat_at="2026-03-02T10:00:00Z",
            os_info="Ubuntu 22.04",
            uptime_seconds=7200,
            active_tasks=3,
            resources=ResourceInfo(
                cpu_usage_percent=75.0,
                memory_usage_percent=80.0,
                disk_usage_percent=50.0,
                disk_free_gb=200.0,
            ),
        )
        assert summary.uptime_seconds == 7200
        assert summary.resources is not None
        assert summary.resources.cpu_usage_percent == 75.0


class TestAgentListResponse:
    """Tests for AgentListResponse DTO."""

    def test_empty_list(self) -> None:
        response = AgentListResponse(agents=[], total=0, online_count=0)
        assert response.total == 0
        assert response.online_count == 0

    def test_list_with_agents(self) -> None:
        agents = [
            AgentSummary(
                host_id="agent-1",
                status=AgentStatus.ONLINE,
                capabilities=[AgentCapability.DOCKER],
            ),
            AgentSummary(
                host_id="agent-2",
                status=AgentStatus.OFFLINE,
                capabilities=[],
            ),
        ]
        response = AgentListResponse(agents=agents, total=2, online_count=1)
        assert response.total == 2
        assert response.online_count == 1
        assert len(response.agents) == 2


class TestAgentDetailResponse:
    """Tests for AgentDetailResponse DTO."""

    def test_valid_detail_response(self) -> None:
        detail = AgentDetailResponse(
            host_id="macbook-pro",
            status=AgentStatus.ONLINE,
            capabilities=[AgentCapability.DOCKER, AgentCapability.MAESTRO_IOS],
            registered_at="2026-03-02T09:00:00Z",
        )
        assert detail.host_id == "macbook-pro"
        assert detail.registered_at == "2026-03-02T09:00:00Z"
        assert detail.metadata == {}

    def test_detail_response_with_metadata(self) -> None:
        detail = AgentDetailResponse(
            host_id="ubuntu-dev",
            status=AgentStatus.BUSY,
            capabilities=[],
            registered_at="2026-03-02T09:00:00Z",
            metadata={"custom_key": "custom_value"},
        )
        assert detail.metadata["custom_key"] == "custom_value"
