"""API Contract tests for agent endpoints.

Validates that backend agent endpoints match the contracts in
shared/api-contracts/rest/v1/agents.json and
shared/api-contracts/ws/agent-messages.json.
"""

import json
from pathlib import Path

from app.schemas.agent import (
    AgentCapability,
    AgentDetailResponse,
    AgentHeartbeatPayload,
    AgentListResponse,
    AgentRegisterAckPayload,
    AgentRegisterPayload,
    AgentStatus,
    ResourceInfo,
)

_REPO_ROOT = Path(__file__).resolve().parents[4]
REST_CONTRACT = _REPO_ROOT / "shared" / "api-contracts" / "rest" / "v1" / "agents.json"
WS_CONTRACT = _REPO_ROOT / "shared" / "api-contracts" / "ws" / "agent-messages.json"


def _load_rest_contract() -> dict[str, object]:
    with open(REST_CONTRACT) as f:
        return json.load(f)  # type: ignore[no-any-return]


def _load_ws_contract() -> dict[str, object]:
    with open(WS_CONTRACT) as f:
        return json.load(f)  # type: ignore[no-any-return]


class TestRestEndpointRegistration:
    """Verify that REST endpoints declared in the contract exist in the app."""

    def test_list_agents_endpoint_registered(self) -> None:
        """GET /api/v1/agents should be registered in the FastAPI app."""
        from app.main import app

        routes = {(r.path, ",".join(r.methods or [])) for r in app.routes if hasattr(r, "methods")}
        assert ("/api/v1/agents", "GET") in routes

    def test_get_agent_endpoint_registered(self) -> None:
        """GET /api/v1/agents/{host_id} should be registered in the FastAPI app."""
        from app.main import app

        paths = [r.path for r in app.routes if hasattr(r, "methods")]
        assert "/api/v1/agents/{host_id}" in paths


class TestRestContractResponseFields:
    """Verify response schema fields match the contract."""

    def test_list_response_has_required_fields(self) -> None:
        """AgentListResponse should have all contract-required fields."""
        contract = _load_rest_contract()
        endpoints = contract["endpoints"]  # type: ignore[index]
        list_ep = endpoints[0]  # GET /api/v1/agents
        required = list_ep["responseBody"]["required"]

        model_fields = set(AgentListResponse.model_fields.keys())
        for field in required:
            assert field in model_fields, f"Missing field: {field}"

    def test_detail_response_has_required_fields(self) -> None:
        """AgentDetailResponse should have all contract-required fields."""
        contract = _load_rest_contract()
        endpoints = contract["endpoints"]  # type: ignore[index]
        detail_ep = endpoints[1]  # GET /api/v1/agents/{host_id}
        required = detail_ep["responseBody"]["required"]

        model_fields = set(AgentDetailResponse.model_fields.keys())
        for field in required:
            assert field in model_fields, f"Missing field: {field}"


class TestRestContractStatusValues:
    """Verify status enum values match the contract."""

    def test_agent_status_values_match_contract(self) -> None:
        """AgentStatus enum values should match contract enum."""
        contract = _load_rest_contract()
        endpoints = contract["endpoints"]  # type: ignore[index]
        list_ep = endpoints[0]
        query_status_enum = list_ep["queryParams"]["properties"]["status"]["enum"]

        status_values = [s.value for s in AgentStatus]
        for value in query_status_enum:
            assert value in status_values, f"Contract status '{value}' not in AgentStatus"


class TestRestContractCapabilityValues:
    """Verify capability enum values match the contract."""

    def test_agent_capability_values_match_contract(self) -> None:
        """AgentCapability enum values should include all contract values."""
        contract = _load_rest_contract()
        endpoints = contract["endpoints"]  # type: ignore[index]
        list_ep = endpoints[0]
        # Dig into agents items -> capabilities -> items -> enum
        agent_props = list_ep["responseBody"]["properties"]["agents"]["items"]["properties"]
        cap_enum = agent_props["capabilities"]["items"]["enum"]

        capability_values = [c.value for c in AgentCapability]
        for value in cap_enum:
            assert value in capability_values, f"Contract capability '{value}' not in enum"


class TestWsContractMessageTypes:
    """Verify WebSocket message schemas match the contract."""

    def test_register_payload_fields_match_contract(self) -> None:
        """AgentRegisterPayload fields should match the ws contract."""
        contract = _load_ws_contract()
        messages = contract["messages"]  # type: ignore[index]
        register_msg = next(m for m in messages if m["type"] == "agent_register")
        required = register_msg["payload"]["required"]

        model_fields = set(AgentRegisterPayload.model_fields.keys())
        for field in required:
            assert field in model_fields, f"Missing register field: {field}"

    def test_register_ack_payload_fields_match_contract(self) -> None:
        """AgentRegisterAckPayload fields should match the ws contract."""
        contract = _load_ws_contract()
        messages = contract["messages"]  # type: ignore[index]
        ack_msg = next(m for m in messages if m["type"] == "agent_register_ack")
        required = ack_msg["payload"]["required"]

        model_fields = set(AgentRegisterAckPayload.model_fields.keys())
        for field in required:
            assert field in model_fields, f"Missing ack field: {field}"

    def test_heartbeat_payload_fields_match_contract(self) -> None:
        """AgentHeartbeatPayload fields should match the ws contract."""
        contract = _load_ws_contract()
        messages = contract["messages"]  # type: ignore[index]
        hb_msg = next(m for m in messages if m["type"] == "agent_heartbeat")
        required = hb_msg["payload"]["required"]

        model_fields = set(AgentHeartbeatPayload.model_fields.keys())
        for field in required:
            assert field in model_fields, f"Missing heartbeat field: {field}"

    def test_resource_info_fields_match_contract(self) -> None:
        """ResourceInfo fields should match heartbeat resources in contract."""
        contract = _load_ws_contract()
        messages = contract["messages"]  # type: ignore[index]
        hb_msg = next(m for m in messages if m["type"] == "agent_heartbeat")
        resource_required = hb_msg["payload"]["properties"]["resources"]["required"]

        model_fields = set(ResourceInfo.model_fields.keys())
        for field in resource_required:
            assert field in model_fields, f"Missing resource field: {field}"
