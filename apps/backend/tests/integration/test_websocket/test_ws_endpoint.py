"""Integration tests for WebSocket endpoint."""

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.main import app


@pytest.fixture
def client() -> TestClient:
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def valid_token() -> str:
    """Create a valid JWT token for testing."""
    return create_access_token(subject="test-user")


@pytest.fixture
def expired_token() -> str:
    """Create an expired JWT token for testing."""
    from datetime import timedelta

    return create_access_token(subject="test-user", expires_delta=timedelta(seconds=-1))


class TestWebSocketConnection:
    """Integration tests for WebSocket connection lifecycle."""

    def test_connect_with_valid_token(
        self, client: TestClient, valid_token: str
    ) -> None:
        """WebSocket should connect successfully with a valid JWT token."""
        with client.websocket_connect(f"/ws?token={valid_token}") as ws:
            # Should receive connection_ack
            data = ws.receive_json()
            assert data["type"] == "connection_ack"
            assert "content" in data
            content = data["content"]
            assert content["user_id"] == "test-user"
            assert "session_id" in content
            assert "server_time" in content

    def test_connect_with_invalid_token(self, client: TestClient) -> None:
        """WebSocket should reject connection with an invalid token."""
        with pytest.raises(Exception):
            with client.websocket_connect("/ws?token=invalid-token"):
                pass

    def test_connect_without_token(self, client: TestClient) -> None:
        """WebSocket should reject connection without a token."""
        with pytest.raises(Exception):
            with client.websocket_connect("/ws"):
                pass

    def test_connection_ack_has_metadata(
        self, client: TestClient, valid_token: str
    ) -> None:
        """connection_ack message should include metadata."""
        with client.websocket_connect(f"/ws?token={valid_token}") as ws:
            data = ws.receive_json()
            assert data["type"] == "connection_ack"
            assert "metadata" in data
            metadata = data["metadata"]
            assert metadata["direction"] == "server_to_client"
            assert "timestamp" in metadata
            assert "session_id" in metadata


class TestWebSocketMessaging:
    """Integration tests for WebSocket message exchange."""

    def test_send_text_message_receives_response(
        self, client: TestClient, valid_token: str
    ) -> None:
        """Sending a text message should receive a text response."""
        with client.websocket_connect(f"/ws?token={valid_token}") as ws:
            # Consume connection_ack
            ws.receive_json()

            # Send text message
            ws.send_json({
                "id": "msg-001",
                "type": "text",
                "content": "Hello RafRaf",
            })
            response = ws.receive_json()
            assert response["type"] == "text"
            assert "content" in response

    def test_send_voice_message_receives_response(
        self, client: TestClient, valid_token: str
    ) -> None:
        """Sending a voice message should receive an acknowledgment."""
        with client.websocket_connect(f"/ws?token={valid_token}") as ws:
            ws.receive_json()  # connection_ack

            ws.send_json({
                "id": "msg-002",
                "type": "voice",
                "content": "Ses mesaji icerigi",
            })
            response = ws.receive_json()
            assert response["type"] == "text"

    def test_send_unknown_type_receives_error(
        self, client: TestClient, valid_token: str
    ) -> None:
        """Sending an unknown message type should receive an error response."""
        with client.websocket_connect(f"/ws?token={valid_token}") as ws:
            ws.receive_json()  # connection_ack

            ws.send_json({
                "id": "msg-003",
                "type": "unknown_type",
                "content": "test",
            })
            response = ws.receive_json()
            assert response["type"] == "error"
            assert response["content"]["error_code"] == "UNKNOWN_MESSAGE_TYPE"

    def test_send_message_without_type_receives_error(
        self, client: TestClient, valid_token: str
    ) -> None:
        """Sending a message without type field should receive an error."""
        with client.websocket_connect(f"/ws?token={valid_token}") as ws:
            ws.receive_json()  # connection_ack

            ws.send_json({
                "id": "msg-004",
                "content": "no type",
            })
            response = ws.receive_json()
            assert response["type"] == "error"
            assert response["content"]["error_code"] == "INVALID_MESSAGE"

    def test_send_server_only_type_receives_error(
        self, client: TestClient, valid_token: str
    ) -> None:
        """Sending a server-only message type should receive an error."""
        with client.websocket_connect(f"/ws?token={valid_token}") as ws:
            ws.receive_json()  # connection_ack

            ws.send_json({
                "id": "msg-005",
                "type": "connection_ack",
                "content": "not allowed",
            })
            response = ws.receive_json()
            assert response["type"] == "error"
            assert response["content"]["error_code"] == "UNSUPPORTED_CLIENT_MESSAGE"


class TestWebSocketPingPong:
    """Integration tests for heartbeat ping/pong."""

    def test_client_ping_receives_pong(
        self, client: TestClient, valid_token: str
    ) -> None:
        """Client-sent ping should receive a pong response."""
        with client.websocket_connect(f"/ws?token={valid_token}") as ws:
            ws.receive_json()  # connection_ack

            ws.send_json({
                "id": "ping-001",
                "type": "ping",
                "content": {"timestamp": "2026-03-02T10:00:00Z"},
            })
            response = ws.receive_json()
            assert response["type"] == "pong"
            assert "content" in response
            assert "timestamp" in response["content"]

    def test_client_pong_is_accepted(
        self, client: TestClient, valid_token: str
    ) -> None:
        """Client-sent pong should be accepted without error."""
        with client.websocket_connect(f"/ws?token={valid_token}") as ws:
            ws.receive_json()  # connection_ack

            # Pong should be silently accepted
            ws.send_json({
                "id": "pong-001",
                "type": "pong",
                "content": {"timestamp": "2026-03-02T10:00:00Z"},
            })
            # Send another message to verify connection is still alive
            ws.send_json({
                "id": "msg-after-pong",
                "type": "text",
                "content": "Still connected",
            })
            response = ws.receive_json()
            assert response["type"] == "text"


class TestWebSocketMultipleMessages:
    """Tests for sending multiple messages in sequence."""

    def test_multiple_text_messages(
        self, client: TestClient, valid_token: str
    ) -> None:
        """Multiple text messages should each receive a response."""
        with client.websocket_connect(f"/ws?token={valid_token}") as ws:
            ws.receive_json()  # connection_ack

            for i in range(3):
                ws.send_json({
                    "id": f"msg-{i}",
                    "type": "text",
                    "content": f"Message {i}",
                })
                response = ws.receive_json()
                assert response["type"] == "text"

    def test_response_has_unique_ids(
        self, client: TestClient, valid_token: str
    ) -> None:
        """Each response should have a unique message ID."""
        with client.websocket_connect(f"/ws?token={valid_token}") as ws:
            ws.receive_json()  # connection_ack

            ids = set()
            for i in range(3):
                ws.send_json({
                    "id": f"msg-{i}",
                    "type": "text",
                    "content": f"Message {i}",
                })
                response = ws.receive_json()
                ids.add(response["id"])

            assert len(ids) == 3

    def test_response_metadata_direction(
        self, client: TestClient, valid_token: str
    ) -> None:
        """Response metadata should have server_to_client direction."""
        with client.websocket_connect(f"/ws?token={valid_token}") as ws:
            ws.receive_json()  # connection_ack

            ws.send_json({
                "id": "msg-meta",
                "type": "text",
                "content": "Test",
            })
            response = ws.receive_json()
            assert response["metadata"]["direction"] == "server_to_client"
