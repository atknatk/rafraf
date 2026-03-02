"""API Contract Tests for WebSocket messages.

Validates that backend WebSocket message schemas match
the contracts defined in shared/api-contracts/ws/websocket-messages.json.
"""

import json
from pathlib import Path

import pytest

from app.schemas.messages import (
    ConnectionAckPayload,
    ErrorPayload,
    MessageDirection,
    MessageType,
    PingPongPayload,
    ProgressPayload,
)

_REPO_ROOT = Path(__file__).resolve().parents[4]
CONTRACT_FILE = _REPO_ROOT / "shared" / "api-contracts" / "ws" / "websocket-messages.json"


@pytest.fixture
def ws_contract() -> dict[str, object]:
    """Load the WebSocket message contract."""
    if not CONTRACT_FILE.exists():
        pytest.skip("WebSocket contract file not found")
    with open(CONTRACT_FILE) as f:
        return json.load(f)  # type: ignore[no-any-return]


def _get_message_def(contract: dict[str, object], msg_type: str) -> dict[str, object] | None:
    """Find a message definition by type in the contract."""
    messages = contract.get("messages", [])
    if not isinstance(messages, list):
        return None
    for msg in messages:
        if isinstance(msg, dict) and msg.get("type") == msg_type:
            return msg  # type: ignore[return-value]
    return None


class TestMessageTypesMatchContract:
    """Verify that all contract message types are defined in the backend."""

    def test_connection_ack_type_exists(self, ws_contract: dict[str, object]) -> None:
        """connection_ack message type should exist in contract and backend."""
        msg_def = _get_message_def(ws_contract, "connection_ack")
        assert msg_def is not None, "connection_ack not in contract"
        assert MessageType.CONNECTION_ACK.value == "connection_ack"

    def test_text_type_exists(self, ws_contract: dict[str, object]) -> None:
        """text message type should exist in contract and backend."""
        msg_def = _get_message_def(ws_contract, "text")
        assert msg_def is not None, "text not in contract"
        assert MessageType.TEXT.value == "text"

    def test_error_type_exists(self, ws_contract: dict[str, object]) -> None:
        """error message type should exist in contract and backend."""
        msg_def = _get_message_def(ws_contract, "error")
        assert msg_def is not None, "error not in contract"
        assert MessageType.ERROR.value == "error"

    def test_progress_type_exists(self, ws_contract: dict[str, object]) -> None:
        """progress message type should exist in contract and backend."""
        msg_def = _get_message_def(ws_contract, "progress")
        assert msg_def is not None, "progress not in contract"
        assert MessageType.PROGRESS.value == "progress"

    def test_ping_type_exists(self, ws_contract: dict[str, object]) -> None:
        """ping message type should exist in contract and backend."""
        msg_def = _get_message_def(ws_contract, "ping")
        assert msg_def is not None, "ping not in contract"
        assert MessageType.PING.value == "ping"

    def test_pong_type_exists(self, ws_contract: dict[str, object]) -> None:
        """pong message type should exist in contract and backend."""
        msg_def = _get_message_def(ws_contract, "pong")
        assert msg_def is not None, "pong not in contract"
        assert MessageType.PONG.value == "pong"


class TestConnectionAckMatchesContract:
    """Verify connection_ack payload matches contract."""

    def test_ack_fields_match_contract(self, ws_contract: dict[str, object]) -> None:
        """ConnectionAckPayload fields should match contract required properties."""
        msg_def = _get_message_def(ws_contract, "connection_ack")
        assert msg_def is not None
        content_schema = msg_def.get("content", {})
        assert isinstance(content_schema, dict)
        contract_required = set(content_schema.get("required", []))
        model_fields = set(ConnectionAckPayload.model_fields.keys())
        assert contract_required.issubset(model_fields), (
            f"Contract requires {contract_required}, model has {model_fields}"
        )


class TestErrorPayloadMatchesContract:
    """Verify error payload matches contract."""

    def test_error_required_fields_match(self, ws_contract: dict[str, object]) -> None:
        """ErrorPayload should have all contract-required fields."""
        msg_def = _get_message_def(ws_contract, "error")
        assert msg_def is not None
        content_schema = msg_def.get("content", {})
        assert isinstance(content_schema, dict)
        contract_required = set(content_schema.get("required", []))
        model_fields = set(ErrorPayload.model_fields.keys())
        assert contract_required.issubset(model_fields), (
            f"Contract requires {contract_required}, model has {model_fields}"
        )


class TestProgressPayloadMatchesContract:
    """Verify progress payload matches contract."""

    def test_progress_required_fields_match(self, ws_contract: dict[str, object]) -> None:
        """ProgressPayload should have all contract-required fields."""
        msg_def = _get_message_def(ws_contract, "progress")
        assert msg_def is not None
        content_schema = msg_def.get("content", {})
        assert isinstance(content_schema, dict)
        contract_required = set(content_schema.get("required", []))
        model_fields = set(ProgressPayload.model_fields.keys())
        assert contract_required.issubset(model_fields), (
            f"Contract requires {contract_required}, model has {model_fields}"
        )


class TestPingPongMatchesContract:
    """Verify ping/pong payload matches contract."""

    def test_ping_required_fields_match(self, ws_contract: dict[str, object]) -> None:
        """PingPongPayload should have all contract-required fields for ping."""
        msg_def = _get_message_def(ws_contract, "ping")
        assert msg_def is not None
        content_schema = msg_def.get("content", {})
        assert isinstance(content_schema, dict)
        contract_required = set(content_schema.get("required", []))
        model_fields = set(PingPongPayload.model_fields.keys())
        assert contract_required.issubset(model_fields), (
            f"Contract requires {contract_required}, model has {model_fields}"
        )


class TestDirectionMatchesContract:
    """Verify message directions match contract definitions."""

    def test_connection_ack_is_server_to_client(self, ws_contract: dict[str, object]) -> None:
        """connection_ack should be server_to_client in contract."""
        msg_def = _get_message_def(ws_contract, "connection_ack")
        assert msg_def is not None
        assert msg_def.get("direction") == "server_to_client"

    def test_error_is_server_to_client(self, ws_contract: dict[str, object]) -> None:
        """error should be server_to_client in contract."""
        msg_def = _get_message_def(ws_contract, "error")
        assert msg_def is not None
        assert msg_def.get("direction") == "server_to_client"

    def test_progress_is_server_to_client(self, ws_contract: dict[str, object]) -> None:
        """progress should be server_to_client in contract."""
        msg_def = _get_message_def(ws_contract, "progress")
        assert msg_def is not None
        assert msg_def.get("direction") == "server_to_client"

    def test_ping_is_bidirectional(self, ws_contract: dict[str, object]) -> None:
        """ping should be bidirectional in contract."""
        msg_def = _get_message_def(ws_contract, "ping")
        assert msg_def is not None
        assert msg_def.get("direction") == "bidirectional"

    def test_direction_enum_covers_contract(self) -> None:
        """MessageDirection should have client_to_server and server_to_client."""
        directions = {d.value for d in MessageDirection}
        assert "client_to_server" in directions
        assert "server_to_client" in directions
