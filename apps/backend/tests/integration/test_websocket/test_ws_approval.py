"""Integration tests for WebSocket approval_response handling."""

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.main import app
from app.schemas.orchestrator import OrchestratorResponse
from app.services.approval_service import ApprovalService, get_approval_service


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
        mock_instance.process_user_message.return_value = mock_response
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


class TestWebSocketApprovalResponse:
    """Integration tests for approval_response WebSocket messages."""

    def test_approval_response_invalid_content_type(
        self, client: TestClient, valid_token: str
    ) -> None:
        """Sending approval_response with non-dict content returns error."""
        with client.websocket_connect(f"/ws?token={valid_token}") as ws:
            ws.receive_json()  # connection_ack

            ws.send_json(
                {
                    "id": "msg-appr-001",
                    "type": "approval_response",
                    "content": "not a dict",
                }
            )
            response = ws.receive_json()
            assert response["type"] == "error"
            assert response["content"]["error_code"] == "INVALID_APPROVAL_RESPONSE"

    def test_approval_response_missing_approval_id(
        self, client: TestClient, valid_token: str
    ) -> None:
        """Sending approval_response without approval_id returns error."""
        with client.websocket_connect(f"/ws?token={valid_token}") as ws:
            ws.receive_json()  # connection_ack

            ws.send_json(
                {
                    "id": "msg-appr-002",
                    "type": "approval_response",
                    "content": {"decision": "approved"},
                }
            )
            response = ws.receive_json()
            assert response["type"] == "error"
            assert response["content"]["error_code"] == "INVALID_APPROVAL_RESPONSE"

    def test_approval_response_missing_decision(
        self, client: TestClient, valid_token: str
    ) -> None:
        """Sending approval_response without decision returns error."""
        with client.websocket_connect(f"/ws?token={valid_token}") as ws:
            ws.receive_json()  # connection_ack

            ws.send_json(
                {
                    "id": "msg-appr-003",
                    "type": "approval_response",
                    "content": {"approval_id": "test-id"},
                }
            )
            response = ws.receive_json()
            assert response["type"] == "error"
            assert response["content"]["error_code"] == "INVALID_APPROVAL_RESPONSE"

    def test_approval_response_invalid_decision_value(
        self, client: TestClient, valid_token: str
    ) -> None:
        """Sending approval_response with invalid decision value returns error."""
        with client.websocket_connect(f"/ws?token={valid_token}") as ws:
            ws.receive_json()  # connection_ack

            ws.send_json(
                {
                    "id": "msg-appr-004",
                    "type": "approval_response",
                    "content": {
                        "approval_id": "test-id",
                        "decision": "maybe",
                    },
                }
            )
            response = ws.receive_json()
            assert response["type"] == "error"
            assert response["content"]["error_code"] == "INVALID_APPROVAL_DECISION"

    def test_approval_response_no_pending_request(
        self, client: TestClient, valid_token: str
    ) -> None:
        """Sending approval_response for non-existent approval returns error."""
        with client.websocket_connect(f"/ws?token={valid_token}") as ws:
            ws.receive_json()  # connection_ack

            ws.send_json(
                {
                    "id": "msg-appr-005",
                    "type": "approval_response",
                    "content": {
                        "approval_id": "nonexistent-id",
                        "decision": "approved",
                    },
                }
            )
            response = ws.receive_json()
            assert response["type"] == "error"
            assert response["content"]["error_code"] == "APPROVAL_NOT_FOUND"

    def test_approval_response_accepted_values(
        self, client: TestClient, valid_token: str
    ) -> None:
        """Test that both 'approved' and 'rejected' are valid decisions."""
        with client.websocket_connect(f"/ws?token={valid_token}") as ws:
            ws.receive_json()  # connection_ack

            # Both should result in APPROVAL_NOT_FOUND (no pending request)
            # but not INVALID_APPROVAL_DECISION
            for decision_val in ("approved", "rejected"):
                ws.send_json(
                    {
                        "id": f"msg-appr-{decision_val}",
                        "type": "approval_response",
                        "content": {
                            "approval_id": f"no-such-{decision_val}",
                            "decision": decision_val,
                        },
                    }
                )
                response = ws.receive_json()
                assert response["type"] == "error"
                assert response["content"]["error_code"] == "APPROVAL_NOT_FOUND"

    def test_approval_response_with_optional_note(
        self, client: TestClient, valid_token: str
    ) -> None:
        """Sending approval_response with note is accepted."""
        with client.websocket_connect(f"/ws?token={valid_token}") as ws:
            ws.receive_json()  # connection_ack

            ws.send_json(
                {
                    "id": "msg-appr-note",
                    "type": "approval_response",
                    "content": {
                        "approval_id": "some-id",
                        "decision": "approved",
                        "note": "Go ahead with deploy",
                    },
                }
            )
            # Should get APPROVAL_NOT_FOUND (not a validation error)
            response = ws.receive_json()
            assert response["type"] == "error"
            assert response["content"]["error_code"] == "APPROVAL_NOT_FOUND"


class TestApprovalServiceSingleton:
    """Tests for the approval service singleton access."""

    def test_get_approval_service_returns_instance(self) -> None:
        service = get_approval_service()
        assert isinstance(service, ApprovalService)

    def test_get_approval_service_returns_same_instance(self) -> None:
        service1 = get_approval_service()
        service2 = get_approval_service()
        assert service1 is service2
