"""Unit tests for WebSocket message schemas."""

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.schemas.messages import (
    ConnectionAckPayload,
    ErrorPayload,
    MessageAttachment,
    MessageDirection,
    MessageMetadata,
    MessageType,
    PingPongPayload,
    ProgressPayload,
    WebSocketMessage,
)


class TestMessageType:
    """Tests for MessageType enum."""

    def test_text_type_value(self) -> None:
        """MessageType.TEXT should have value 'text'."""
        assert MessageType.TEXT.value == "text"

    def test_voice_type_value(self) -> None:
        """MessageType.VOICE should have value 'voice'."""
        assert MessageType.VOICE.value == "voice"

    def test_connection_ack_type_value(self) -> None:
        """MessageType.CONNECTION_ACK should have value 'connection_ack'."""
        assert MessageType.CONNECTION_ACK.value == "connection_ack"

    def test_error_type_value(self) -> None:
        """MessageType.ERROR should have value 'error'."""
        assert MessageType.ERROR.value == "error"

    def test_progress_type_value(self) -> None:
        """MessageType.PROGRESS should have value 'progress'."""
        assert MessageType.PROGRESS.value == "progress"

    def test_ping_type_value(self) -> None:
        """MessageType.PING should have value 'ping'."""
        assert MessageType.PING.value == "ping"

    def test_pong_type_value(self) -> None:
        """MessageType.PONG should have value 'pong'."""
        assert MessageType.PONG.value == "pong"

    def test_all_types_exist(self) -> None:
        """All expected message types should exist."""
        expected = {"text", "voice", "connection_ack", "error", "progress", "ping", "pong"}
        actual = {t.value for t in MessageType}
        assert actual == expected


class TestMessageDirection:
    """Tests for MessageDirection enum."""

    def test_client_to_server_value(self) -> None:
        """MessageDirection.CLIENT_TO_SERVER should have correct value."""
        assert MessageDirection.CLIENT_TO_SERVER.value == "client_to_server"

    def test_server_to_client_value(self) -> None:
        """MessageDirection.SERVER_TO_CLIENT should have correct value."""
        assert MessageDirection.SERVER_TO_CLIENT.value == "server_to_client"


class TestMessageMetadata:
    """Tests for MessageMetadata model."""

    def test_create_metadata_minimal(self) -> None:
        """MessageMetadata should be created with required fields only."""
        meta = MessageMetadata(
            timestamp="2026-03-02T10:00:00Z",
            direction=MessageDirection.CLIENT_TO_SERVER,
        )
        assert meta.timestamp == "2026-03-02T10:00:00Z"
        assert meta.direction == MessageDirection.CLIENT_TO_SERVER
        assert meta.session_id is None
        assert meta.project_id is None

    def test_create_metadata_full(self) -> None:
        """MessageMetadata should accept all optional fields."""
        meta = MessageMetadata(
            timestamp="2026-03-02T10:00:00Z",
            session_id="session-123",
            project_id="proj-456",
            message_id="msg-789",
            direction=MessageDirection.SERVER_TO_CLIENT,
        )
        assert meta.session_id == "session-123"
        assert meta.project_id == "proj-456"
        assert meta.message_id == "msg-789"

    def test_metadata_is_frozen(self) -> None:
        """MessageMetadata should be immutable (frozen)."""
        meta = MessageMetadata(
            timestamp="2026-03-02T10:00:00Z",
            direction=MessageDirection.CLIENT_TO_SERVER,
        )
        with pytest.raises(PydanticValidationError):
            meta.timestamp = "2026-03-02T11:00:00Z"  # type: ignore[misc]


class TestMessageAttachment:
    """Tests for MessageAttachment model."""

    def test_create_attachment(self) -> None:
        """MessageAttachment should be created with required fields."""
        att = MessageAttachment(
            type="image",
            url="s3://bucket/file.png",
            mime_type="image/png",
            size_bytes=102400,
        )
        assert att.type == "image"
        assert att.url == "s3://bucket/file.png"
        assert att.mime_type == "image/png"
        assert att.size_bytes == 102400

    def test_attachment_is_frozen(self) -> None:
        """MessageAttachment should be immutable (frozen)."""
        att = MessageAttachment(
            type="image",
            url="s3://bucket/file.png",
            mime_type="image/png",
            size_bytes=102400,
        )
        with pytest.raises(PydanticValidationError):
            att.type = "file"  # type: ignore[misc]


class TestWebSocketMessage:
    """Tests for WebSocketMessage model."""

    def test_create_text_message(self) -> None:
        """WebSocketMessage should create a text message."""
        msg = WebSocketMessage(
            id="msg-001",
            type=MessageType.TEXT,
            content="Hello",
        )
        assert msg.id == "msg-001"
        assert msg.type == MessageType.TEXT
        assert msg.content == "Hello"

    def test_create_message_with_dict_content(self) -> None:
        """WebSocketMessage should accept dict content."""
        msg = WebSocketMessage(
            id="msg-002",
            type=MessageType.ERROR,
            content={"error_code": "TEST", "message": "Test error"},
        )
        assert isinstance(msg.content, dict)

    def test_auto_generated_id(self) -> None:
        """WebSocketMessage should auto-generate ID if not provided."""
        msg = WebSocketMessage(type=MessageType.TEXT, content="Hello")
        assert msg.id is not None
        assert len(msg.id) > 0

    def test_message_is_frozen(self) -> None:
        """WebSocketMessage should be immutable (frozen)."""
        msg = WebSocketMessage(type=MessageType.TEXT, content="Hello")
        with pytest.raises(PydanticValidationError):
            msg.content = "Modified"  # type: ignore[misc]

    def test_message_with_metadata(self) -> None:
        """WebSocketMessage should include metadata."""
        meta = MessageMetadata(
            timestamp="2026-03-02T10:00:00Z",
            direction=MessageDirection.CLIENT_TO_SERVER,
        )
        msg = WebSocketMessage(
            type=MessageType.TEXT,
            content="Hello",
            metadata=meta,
        )
        assert msg.metadata is not None
        assert msg.metadata.direction == MessageDirection.CLIENT_TO_SERVER

    def test_message_with_attachments(self) -> None:
        """WebSocketMessage should include attachments list."""
        att = MessageAttachment(
            type="image",
            url="s3://bucket/img.png",
            mime_type="image/png",
            size_bytes=1024,
        )
        msg = WebSocketMessage(
            type=MessageType.TEXT,
            content="See image",
            attachments=[att],
        )
        assert msg.attachments is not None
        assert len(msg.attachments) == 1

    def test_message_serialization(self) -> None:
        """WebSocketMessage should serialize to dict correctly."""
        msg = WebSocketMessage(
            id="test-id",
            type=MessageType.TEXT,
            content="Hello",
        )
        data = msg.model_dump()
        assert data["id"] == "test-id"
        assert data["type"] == "text"
        assert data["content"] == "Hello"


class TestConnectionAckPayload:
    """Tests for ConnectionAckPayload model."""

    def test_create_ack_payload(self) -> None:
        """ConnectionAckPayload should have user_id, session_id, server_time."""
        payload = ConnectionAckPayload(
            user_id="user-1",
            session_id="sess-1",
            server_time="2026-03-02T10:00:00Z",
        )
        assert payload.user_id == "user-1"
        assert payload.session_id == "sess-1"
        assert payload.server_time == "2026-03-02T10:00:00Z"

    def test_ack_payload_is_frozen(self) -> None:
        """ConnectionAckPayload should be immutable."""
        payload = ConnectionAckPayload(
            user_id="user-1",
            session_id="sess-1",
            server_time="2026-03-02T10:00:00Z",
        )
        with pytest.raises(PydanticValidationError):
            payload.user_id = "user-2"  # type: ignore[misc]


class TestErrorPayload:
    """Tests for ErrorPayload model."""

    def test_create_error_payload_minimal(self) -> None:
        """ErrorPayload should have required fields."""
        payload = ErrorPayload(
            error_code="TEST_ERROR",
            message="Something went wrong",
        )
        assert payload.error_code == "TEST_ERROR"
        assert payload.message == "Something went wrong"
        assert payload.recoverable is True
        assert payload.details is None
        assert payload.suggestion is None

    def test_create_error_payload_full(self) -> None:
        """ErrorPayload should accept all optional fields."""
        payload = ErrorPayload(
            error_code="CRITICAL",
            message="Fatal error",
            details="Stack trace here",
            suggestion="Restart the server",
            recoverable=False,
        )
        assert payload.recoverable is False
        assert payload.details == "Stack trace here"
        assert payload.suggestion == "Restart the server"


class TestProgressPayload:
    """Tests for ProgressPayload model."""

    def test_create_progress_payload(self) -> None:
        """ProgressPayload should have task progress fields."""
        payload = ProgressPayload(
            task="Building Docker image",
            step=3,
            total_steps=10,
            percentage=30,
        )
        assert payload.task == "Building Docker image"
        assert payload.step == 3
        assert payload.total_steps == 10
        assert payload.percentage == 30
        assert payload.details is None

    def test_progress_payload_with_details(self) -> None:
        """ProgressPayload should accept optional details."""
        payload = ProgressPayload(
            task="Deploying",
            step=1,
            total_steps=3,
            percentage=33,
            details="Pulling base image",
        )
        assert payload.details == "Pulling base image"


class TestPingPongPayload:
    """Tests for PingPongPayload model."""

    def test_create_ping_payload(self) -> None:
        """PingPongPayload should have a timestamp."""
        payload = PingPongPayload(timestamp="2026-03-02T10:00:00Z")
        assert payload.timestamp == "2026-03-02T10:00:00Z"

    def test_ping_payload_is_frozen(self) -> None:
        """PingPongPayload should be immutable."""
        payload = PingPongPayload(timestamp="2026-03-02T10:00:00Z")
        with pytest.raises(PydanticValidationError):
            payload.timestamp = "2026-03-02T11:00:00Z"  # type: ignore[misc]
