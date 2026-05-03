"""Integration tests for WebSocket endpoint."""

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.core.security import create_access_token
from app.main import app
from app.schemas.orchestrator import OrchestratorResponse


def _receive_until(ws: object, target_type: str, max_messages: int = 10) -> dict:  # type: ignore[type-arg]
    """Drain messages until the expected type is received (skips progress/stream events)."""
    for _ in range(max_messages):
        msg = ws.receive_json()  # type: ignore[attr-defined]
        if msg["type"] == target_type:
            return msg  # type: ignore[no-any-return]
    raise AssertionError(
        f"Did not receive message of type '{target_type}' within {max_messages} messages"
    )


@pytest.fixture
def mock_orchestrator() -> Generator[AsyncMock, None, None]:
    """Mock OrchestratorService to avoid real Anthropic API calls in CI."""
    mock_response = OrchestratorResponse(
        session_id="test-session",
        response_text="Mocked AI response",
        model_used="claude-haiku-4-5-20251001",
        tokens_input=10,
        tokens_output=5,
        tool_calls_count=0,
    )
    with patch(
        "app.api.routes.websocket.OrchestratorService",
        autospec=True,
    ) as mock_cls:
        mock_instance = AsyncMock()
        # Cover all processing paths (claude_code, streaming API, legacy)
        mock_instance.process_user_message.return_value = mock_response
        mock_instance.process_user_message_streaming.return_value = mock_response
        mock_instance.process_with_claude_code.return_value = mock_response
        mock_cls.return_value = mock_instance
        yield mock_instance


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

    def test_connect_with_valid_token(self, client: TestClient, valid_token: str) -> None:
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
        with (
            pytest.raises(WebSocketDisconnect),
            client.websocket_connect("/ws?token=invalid-token"),
        ):
            pass

    def test_connect_without_token(self, client: TestClient) -> None:
        """WebSocket should reject connection without a token."""
        with (
            pytest.raises((WebSocketDisconnect, KeyError)),
            client.websocket_connect("/ws"),
        ):
            pass

    def test_connection_ack_has_metadata(self, client: TestClient, valid_token: str) -> None:
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

    @pytest.mark.usefixtures("mock_orchestrator")
    def test_send_text_message_receives_response(
        self, client: TestClient, valid_token: str
    ) -> None:
        """Sending a text message should receive a text response."""
        with client.websocket_connect(f"/ws?token={valid_token}") as ws:
            # Consume connection_ack
            ws.receive_json()

            # Send text message
            ws.send_json(
                {
                    "id": "msg-001",
                    "type": "text",
                    "content": "Hello RafRaf",
                }
            )
            # Server now sends chat.stream_end as the final response
            response = _receive_until(ws, "chat.stream_end")
            assert response["type"] == "chat.stream_end"
            assert "content" in response

    @pytest.mark.usefixtures("mock_orchestrator")
    def test_send_voice_message_rejected(self, client: TestClient, valid_token: str) -> None:
        """Sending a voice message should be rejected (voice fully removed in T0.9)."""
        with client.websocket_connect(f"/ws?token={valid_token}") as ws:
            ws.receive_json()  # connection_ack

            ws.send_json(
                {
                    "id": "msg-002",
                    "type": "voice",
                    "content": "Ses mesaji icerigi",
                }
            )
            response = ws.receive_json()
            assert response["type"] == "error"
            assert response["content"]["error_code"] == "UNKNOWN_MESSAGE_TYPE"

    def test_send_unknown_type_receives_error(self, client: TestClient, valid_token: str) -> None:
        """Sending an unknown message type should receive an error response."""
        with client.websocket_connect(f"/ws?token={valid_token}") as ws:
            ws.receive_json()  # connection_ack

            ws.send_json(
                {
                    "id": "msg-003",
                    "type": "unknown_type",
                    "content": "test",
                }
            )
            response = ws.receive_json()
            assert response["type"] == "error"
            assert response["content"]["error_code"] == "UNKNOWN_MESSAGE_TYPE"

    def test_send_message_without_type_receives_error(
        self, client: TestClient, valid_token: str
    ) -> None:
        """Sending a message without type field should receive an error."""
        with client.websocket_connect(f"/ws?token={valid_token}") as ws:
            ws.receive_json()  # connection_ack

            ws.send_json(
                {
                    "id": "msg-004",
                    "content": "no type",
                }
            )
            response = ws.receive_json()
            assert response["type"] == "error"
            assert response["content"]["error_code"] == "INVALID_MESSAGE"

    def test_send_server_only_type_receives_error(
        self, client: TestClient, valid_token: str
    ) -> None:
        """Sending a server-only message type should receive an error."""
        with client.websocket_connect(f"/ws?token={valid_token}") as ws:
            ws.receive_json()  # connection_ack

            ws.send_json(
                {
                    "id": "msg-005",
                    "type": "connection_ack",
                    "content": "not allowed",
                }
            )
            response = ws.receive_json()
            assert response["type"] == "error"
            assert response["content"]["error_code"] == "UNSUPPORTED_CLIENT_MESSAGE"


class TestWebSocketPingPong:
    """Integration tests for heartbeat ping/pong."""

    def test_client_ping_receives_pong(self, client: TestClient, valid_token: str) -> None:
        """Client-sent ping should receive a pong response."""
        with client.websocket_connect(f"/ws?token={valid_token}") as ws:
            ws.receive_json()  # connection_ack

            ws.send_json(
                {
                    "id": "ping-001",
                    "type": "ping",
                    "content": {"timestamp": "2026-03-02T10:00:00Z"},
                }
            )
            response = ws.receive_json()
            assert response["type"] == "pong"
            assert "content" in response
            assert "timestamp" in response["content"]

    @pytest.mark.usefixtures("mock_orchestrator")
    def test_client_pong_is_accepted(self, client: TestClient, valid_token: str) -> None:
        """Client-sent pong should be accepted without error."""
        with client.websocket_connect(f"/ws?token={valid_token}") as ws:
            ws.receive_json()  # connection_ack

            # Pong should be silently accepted
            ws.send_json(
                {
                    "id": "pong-001",
                    "type": "pong",
                    "content": {"timestamp": "2026-03-02T10:00:00Z"},
                }
            )
            # Send another message to verify connection is still alive
            ws.send_json(
                {
                    "id": "msg-after-pong",
                    "type": "text",
                    "content": "Still connected",
                }
            )
            response = _receive_until(ws, "chat.stream_end")
            assert response["type"] == "chat.stream_end"


class TestWebSocketMultipleMessages:
    """Tests for sending multiple messages in sequence."""

    @pytest.mark.usefixtures("mock_orchestrator")
    def test_multiple_text_messages(self, client: TestClient, valid_token: str) -> None:
        """Multiple text messages should each receive a response."""
        with client.websocket_connect(f"/ws?token={valid_token}") as ws:
            ws.receive_json()  # connection_ack

            for i in range(3):
                ws.send_json(
                    {
                        "id": f"msg-{i}",
                        "type": "text",
                        "content": f"Message {i}",
                    }
                )
                response = _receive_until(ws, "chat.stream_end")
                assert response["type"] == "chat.stream_end"

    @pytest.mark.usefixtures("mock_orchestrator")
    def test_response_has_unique_ids(self, client: TestClient, valid_token: str) -> None:
        """Each response should have a unique message ID."""
        with client.websocket_connect(f"/ws?token={valid_token}") as ws:
            ws.receive_json()  # connection_ack

            ids = set()
            for i in range(3):
                ws.send_json(
                    {
                        "id": f"msg-{i}",
                        "type": "text",
                        "content": f"Message {i}",
                    }
                )
                response = ws.receive_json()
                ids.add(response["id"])

            assert len(ids) == 3

    @pytest.mark.usefixtures("mock_orchestrator")
    def test_response_metadata_direction(self, client: TestClient, valid_token: str) -> None:
        """Response metadata should have server_to_client direction."""
        with client.websocket_connect(f"/ws?token={valid_token}") as ws:
            ws.receive_json()  # connection_ack

            ws.send_json(
                {
                    "id": "msg-meta",
                    "type": "text",
                    "content": "Test",
                }
            )
            response = ws.receive_json()
            assert response["metadata"]["direction"] == "server_to_client"


class TestApprovalResponseAckEnvelope:
    """V1.x WS reliability — ack envelope emission for approval_response.

    iOS sends ``approval_response`` with a ``metadata.client_message_id`` UUID
    over a half-dead WebSocket and waits for a backend ``ack`` echoing that
    id before clearing its pending-ack table. On ack timeout iOS retries
    with the SAME id; backend dedups so the second arrival re-acks but does
    not double-process the underlying business logic.
    """

    def test_approval_response_emits_ack_when_client_message_id_present(
        self, client: TestClient, valid_token: str
    ) -> None:
        """ack envelope MUST be the first message after a valid approval_response."""
        approval_id = "ack-test-approval-001"
        client_msg_id = "client-uuid-abc"

        # Mock submit_decision to short-circuit the bridge fallback path
        # (so we get a deterministic post-ack response).
        with patch(
            "app.api.routes.websocket.get_approval_service",
        ) as mock_get_svc:
            mock_svc = AsyncMock()
            # get_pending_approval is SYNC on the real service; AsyncMock would
            # return a coroutine and break the `pending_snapshot is not None`
            # branch downstream. Replace with a plain MagicMock returning None.
            mock_svc.get_pending_approval = MagicMock(return_value=None)
            mock_svc.submit_decision.return_value = True  # "submitted" so no bridge fallback
            mock_get_svc.return_value = mock_svc

            with client.websocket_connect(f"/ws?token={valid_token}") as ws:
                ws.receive_json()  # connection_ack

                ws.send_json(
                    {
                        "id": "msg-ack-001",
                        "type": "approval_response",
                        "content": {
                            "approval_id": approval_id,
                            "decision": "approved",
                        },
                        "metadata": {
                            "client_message_id": client_msg_id,
                        },
                    }
                )

                # ack MUST arrive first — before any business-logic response.
                first = ws.receive_json()
                assert first["type"] == "ack", f"Expected ack first, got {first['type']}"
                assert first["metadata"]["client_message_id"] == client_msg_id
                assert first["metadata"]["ack_for_type"] == "approval_response"
                assert first["metadata"]["direction"] == "server_to_client"
                assert first["content"] == {}

    def test_approval_response_no_ack_when_client_message_id_absent(
        self, client: TestClient, valid_token: str
    ) -> None:
        """Backwards-compat: older iOS clients omit client_message_id → NO ack."""
        with client.websocket_connect(f"/ws?token={valid_token}") as ws:
            ws.receive_json()  # connection_ack

            ws.send_json(
                {
                    "id": "msg-no-cmid",
                    "type": "approval_response",
                    "content": {
                        "approval_id": "no-such-id",
                        "decision": "approved",
                    },
                    # No metadata.client_message_id — older iOS shape.
                }
            )

            response = ws.receive_json()
            # First (and only) response is the existing APPROVAL_NOT_FOUND error,
            # NOT an ack. This proves the ack emission is gated on cmid presence.
            assert response["type"] == "error"
            assert response["content"]["error_code"] == "APPROVAL_NOT_FOUND"

    def test_approval_response_dedup_via_repeat_client_message_id(
        self, client: TestClient, valid_token: str
    ) -> None:
        """Same client_message_id twice → both ack, but submit_decision called once."""
        approval_id = "dedup-test-approval-002"
        client_msg_id = "client-uuid-dedup"

        with patch(
            "app.api.routes.websocket.get_approval_service",
        ) as mock_get_svc:
            mock_svc = AsyncMock()
            # get_pending_approval is SYNC on the real service; AsyncMock would
            # return a coroutine and break the `pending_snapshot is not None`
            # branch downstream. Replace with a plain MagicMock returning None.
            mock_svc.get_pending_approval = MagicMock(return_value=None)
            mock_svc.submit_decision.return_value = True
            mock_get_svc.return_value = mock_svc

            with client.websocket_connect(f"/ws?token={valid_token}") as ws:
                ws.receive_json()  # connection_ack

                payload = {
                    "id": "msg-dedup-001",
                    "type": "approval_response",
                    "content": {
                        "approval_id": approval_id,
                        "decision": "approved",
                    },
                    "metadata": {
                        "client_message_id": client_msg_id,
                    },
                }

                # First send: ack + business logic (submit_decision called once).
                ws.send_json(payload)
                first_ack = ws.receive_json()
                assert first_ack["type"] == "ack"
                assert first_ack["metadata"]["client_message_id"] == client_msg_id

                # Second send (iOS retry on missed ack): ack again, but no
                # double-processing. Send a probe ping after to drain any
                # spurious error envelope that would indicate double-processing.
                ws.send_json(payload)
                second_ack = ws.receive_json()
                assert second_ack["type"] == "ack", (
                    f"Expected ack on retry, got {second_ack['type']}"
                )
                assert second_ack["metadata"]["client_message_id"] == client_msg_id

                # Probe: send a ping; if the next message is the pong, no
                # spurious error envelope was emitted between the two acks.
                ws.send_json(
                    {
                        "id": "probe-ping",
                        "type": "ping",
                        "content": {"timestamp": "2026-05-03T00:00:00Z"},
                    }
                )
                probe = ws.receive_json()
                assert probe["type"] == "pong", (
                    f"Expected pong after retry-ack, got {probe['type']} "
                    f"— suggests dedup did not short-circuit business logic"
                )

            # submit_decision MUST have been called only ONCE despite two retries.
            assert mock_svc.submit_decision.call_count == 1, (
                f"Expected submit_decision called exactly once "
                f"(dedup short-circuit), got {mock_svc.submit_decision.call_count}"
            )
