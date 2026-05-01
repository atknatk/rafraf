"""Unit tests for WebSocket message schemas."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

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
    RateLimitInfoPayload,
    SessionInitPayload,
    SessionPrOpenedPayload,
    SessionTitlePayload,
    SubagentCompletedPayload,
    SubagentProgressPayload,
    SubagentSpawnedPayload,
    UsageReportPayload,
    WebSocketMessage,
)


class TestMessageType:
    """Tests for MessageType enum."""

    def test_text_type_value(self) -> None:
        """MessageType.TEXT should have value 'text'."""
        assert MessageType.TEXT.value == "text"

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
        expected = {
            "text",
            "connection_ack",
            "error",
            "progress",
            "ping",
            "pong",
            "status",
            "question",
            "action_result",
            "approval_response",
            "chat.stream",
            "chat.stream_end",
            "code.diff",
            "suggestion",
            "typing.start",
            "typing.end",
            "task_status",
            "stream.cancel",
            "stream.cancelled",
            # Agent Teams (T1.5)
            "session.init",
            "subagent.spawned",
            "subagent.progress",
            "subagent.completed",
            "rate_limit.info",
            "session.title",
            "session.pr_opened",
            "usage.report",
        }
        actual = {t.value for t in MessageType}
        assert actual == expected

    def test_agent_teams_type_values(self) -> None:
        """Each Agent Teams MessageType has the documented string value."""
        assert MessageType.SESSION_INIT.value == "session.init"
        assert MessageType.SUBAGENT_SPAWNED.value == "subagent.spawned"
        assert MessageType.SUBAGENT_PROGRESS.value == "subagent.progress"
        assert MessageType.SUBAGENT_COMPLETED.value == "subagent.completed"
        assert MessageType.RATE_LIMIT_INFO.value == "rate_limit.info"
        assert MessageType.SESSION_TITLE.value == "session.title"
        assert MessageType.SESSION_PR_OPENED.value == "session.pr_opened"
        assert MessageType.USAGE_REPORT.value == "usage.report"


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


# ---------------------------------------------------------------------------
# Agent Teams payloads (T1.5)
# ---------------------------------------------------------------------------


class TestSessionInitPayload:
    """Tests for SessionInitPayload model."""

    def test_create_full(self) -> None:
        """SessionInitPayload constructs with all required fields."""
        ts = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
        payload = SessionInitPayload(
            session_id="abc-123",
            model="claude-opus-4-7",
            permission_mode="acceptEdits",
            api_key_source="subscription",
            cwd="/Users/dev/project",
            agent_teams_enabled=True,
            initialized_at=ts,
        )
        assert payload.session_id == "abc-123"
        assert payload.model == "claude-opus-4-7"
        assert payload.permission_mode == "acceptEdits"
        assert payload.api_key_source == "subscription"
        assert payload.cwd == "/Users/dev/project"
        assert payload.agent_teams_enabled is True
        assert payload.initialized_at == ts

    def test_round_trip_json(self) -> None:
        """SessionInitPayload survives a JSON dump/load round-trip."""
        original = SessionInitPayload(
            session_id="abc-123",
            model="claude-opus-4-7",
            permission_mode="acceptEdits",
            api_key_source="subscription",
            cwd="/Users/dev/project",
            agent_teams_enabled=True,
            initialized_at=datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC),
        )
        json_str = original.model_dump_json()
        restored = SessionInitPayload.model_validate_json(json_str)
        assert restored == original

    def test_missing_required_field_rejected(self) -> None:
        """Missing required field raises ValidationError."""
        with pytest.raises(PydanticValidationError):
            SessionInitPayload.model_validate(
                {
                    "session_id": "abc",
                    "model": "claude-opus-4-7",
                    "permission_mode": "acceptEdits",
                    "api_key_source": "subscription",
                    # missing: cwd, agent_teams_enabled, initialized_at
                }
            )

    def test_is_frozen(self) -> None:
        """SessionInitPayload is immutable."""
        payload = SessionInitPayload(
            session_id="abc",
            model="claude-opus-4-7",
            permission_mode="acceptEdits",
            api_key_source="subscription",
            cwd="/x",
            agent_teams_enabled=True,
            initialized_at=datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC),
        )
        with pytest.raises(PydanticValidationError):
            payload.model = "claude-sonnet-4-7"  # type: ignore[misc]


class TestSubagentSpawnedPayload:
    """Tests for SubagentSpawnedPayload model."""

    def test_create_minimal(self) -> None:
        """SubagentSpawnedPayload constructs with only required fields."""
        ts = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
        payload = SubagentSpawnedPayload(
            task_id="task-001",
            name="frontend-impl",
            prompt_preview="Implement the cart UI",
            started_at=ts,
        )
        assert payload.task_id == "task-001"
        assert payload.name == "frontend-impl"
        assert payload.description is None
        assert payload.subagent_type is None
        assert payload.isolation is None
        assert payload.started_at == ts

    def test_create_full(self) -> None:
        """SubagentSpawnedPayload accepts all optional fields."""
        ts = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
        payload = SubagentSpawnedPayload(
            task_id="task-001",
            name="frontend-impl",
            description="UI work for cart",
            prompt_preview="Implement the cart UI",
            subagent_type="general-purpose",
            isolation="worktree",
            started_at=ts,
        )
        assert payload.description == "UI work for cart"
        assert payload.subagent_type == "general-purpose"
        assert payload.isolation == "worktree"

    def test_round_trip_json(self) -> None:
        """SubagentSpawnedPayload survives JSON round-trip."""
        original = SubagentSpawnedPayload(
            task_id="task-001",
            name="frontend-impl",
            description="UI",
            prompt_preview="...",
            subagent_type="general-purpose",
            isolation="worktree",
            started_at=datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC),
        )
        restored = SubagentSpawnedPayload.model_validate_json(original.model_dump_json())
        assert restored == original

    def test_missing_required_field_rejected(self) -> None:
        """Missing task_id raises ValidationError."""
        with pytest.raises(PydanticValidationError):
            SubagentSpawnedPayload.model_validate(
                {
                    "name": "frontend-impl",
                    "prompt_preview": "...",
                    "started_at": "2026-05-01T12:00:00Z",
                }
            )


class TestSubagentProgressPayload:
    """Tests for SubagentProgressPayload model."""

    def test_create(self) -> None:
        """SubagentProgressPayload constructs with required fields."""
        ts = datetime(2026, 5, 1, 12, 5, 0, tzinfo=UTC)
        payload = SubagentProgressPayload(
            task_id="task-001",
            status="in_progress",
            activity="Editing config.toml",
            updated_at=ts,
        )
        assert payload.task_id == "task-001"
        assert payload.status == "in_progress"
        assert payload.activity == "Editing config.toml"
        assert payload.updated_at == ts

    def test_round_trip_json(self) -> None:
        """SubagentProgressPayload survives JSON round-trip."""
        original = SubagentProgressPayload(
            task_id="task-001",
            status="queued",
            activity="Waiting for runner",
            updated_at=datetime(2026, 5, 1, 12, 5, 0, tzinfo=UTC),
        )
        restored = SubagentProgressPayload.model_validate_json(original.model_dump_json())
        assert restored == original

    def test_missing_field_rejected(self) -> None:
        """Missing activity raises ValidationError."""
        with pytest.raises(PydanticValidationError):
            SubagentProgressPayload.model_validate(
                {
                    "task_id": "task-001",
                    "status": "in_progress",
                    "updated_at": "2026-05-01T12:05:00Z",
                }
            )


class TestSubagentCompletedPayload:
    """Tests for SubagentCompletedPayload model."""

    def test_create_completed(self) -> None:
        """SubagentCompletedPayload constructs for a successful completion."""
        ts = datetime(2026, 5, 1, 12, 30, 0, tzinfo=UTC)
        payload = SubagentCompletedPayload(
            task_id="task-001",
            status="completed",
            summary="Implemented cart UI with 3 components",
            total_tokens=12_345,
            tool_uses=42,
            duration_ms=180_000,
            completed_at=ts,
        )
        assert payload.task_id == "task-001"
        assert payload.status == "completed"
        assert payload.summary == "Implemented cart UI with 3 components"
        assert payload.total_tokens == 12_345
        assert payload.tool_uses == 42
        assert payload.duration_ms == 180_000
        assert payload.completed_at == ts

    def test_create_failed_no_summary(self) -> None:
        """SubagentCompletedPayload allows failed status without summary."""
        payload = SubagentCompletedPayload(
            task_id="task-002",
            status="failed",
            total_tokens=100,
            tool_uses=1,
            duration_ms=5_000,
            completed_at=datetime(2026, 5, 1, 12, 30, 0, tzinfo=UTC),
        )
        assert payload.summary is None
        assert payload.status == "failed"

    def test_round_trip_json(self) -> None:
        """SubagentCompletedPayload survives JSON round-trip."""
        original = SubagentCompletedPayload(
            task_id="task-001",
            status="completed",
            summary="ok",
            total_tokens=1,
            tool_uses=1,
            duration_ms=1,
            completed_at=datetime(2026, 5, 1, 12, 30, 0, tzinfo=UTC),
        )
        restored = SubagentCompletedPayload.model_validate_json(original.model_dump_json())
        assert restored == original

    def test_missing_field_rejected(self) -> None:
        """Missing duration_ms raises ValidationError."""
        with pytest.raises(PydanticValidationError):
            SubagentCompletedPayload.model_validate(
                {
                    "task_id": "task-001",
                    "status": "completed",
                    "total_tokens": 1,
                    "tool_uses": 1,
                    "completed_at": "2026-05-01T12:30:00Z",
                }
            )


class TestRateLimitInfoPayload:
    """Tests for RateLimitInfoPayload model."""

    def test_create_allowed(self) -> None:
        """RateLimitInfoPayload constructs in 'allowed' state."""
        payload = RateLimitInfoPayload(
            status="allowed",
            rate_limit_type="five_hour",
            resets_at=1_777_000_000,
            overage_status="not_using",
            is_using_overage=False,
        )
        assert payload.status == "allowed"
        assert payload.rate_limit_type == "five_hour"
        assert payload.resets_at == 1_777_000_000
        assert payload.overage_status == "not_using"
        assert payload.is_using_overage is False

    def test_round_trip_json(self) -> None:
        """RateLimitInfoPayload survives JSON round-trip."""
        original = RateLimitInfoPayload(
            status="limited",
            rate_limit_type="five_hour",
            resets_at=1_777_000_000,
            overage_status="opted_in",
            is_using_overage=True,
        )
        restored = RateLimitInfoPayload.model_validate_json(original.model_dump_json())
        assert restored == original

    def test_missing_field_rejected(self) -> None:
        """Missing is_using_overage raises ValidationError."""
        with pytest.raises(PydanticValidationError):
            RateLimitInfoPayload.model_validate(
                {
                    "status": "allowed",
                    "rate_limit_type": "five_hour",
                    "resets_at": 1,
                    "overage_status": "not_using",
                }
            )


class TestSessionTitlePayload:
    """Tests for SessionTitlePayload model."""

    def test_create(self) -> None:
        """SessionTitlePayload constructs with a UUID session_id."""
        sid = uuid4()
        ts = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
        payload = SessionTitlePayload(
            session_id=sid,
            ai_title="Refactor cart checkout flow",
            generated_at=ts,
        )
        assert payload.session_id == sid
        assert payload.ai_title == "Refactor cart checkout flow"
        assert payload.generated_at == ts

    def test_round_trip_json(self) -> None:
        """SessionTitlePayload survives JSON round-trip."""
        original = SessionTitlePayload(
            session_id=UUID("12345678-1234-5678-1234-567812345678"),
            ai_title="Refactor",
            generated_at=datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC),
        )
        restored = SessionTitlePayload.model_validate_json(original.model_dump_json())
        assert restored == original

    def test_invalid_uuid_rejected(self) -> None:
        """Non-UUID session_id raises ValidationError."""
        with pytest.raises(PydanticValidationError):
            SessionTitlePayload.model_validate(
                {
                    "session_id": "not-a-uuid",
                    "ai_title": "x",
                    "generated_at": "2026-05-01T12:00:00Z",
                }
            )


class TestSessionPrOpenedPayload:
    """Tests for SessionPrOpenedPayload model."""

    def test_create(self) -> None:
        """SessionPrOpenedPayload constructs with all fields."""
        sid = uuid4()
        ts = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
        payload = SessionPrOpenedPayload(
            session_id=sid,
            pr_number=42,
            pr_url="https://github.com/owner/repo/pull/42",
            pr_repository="owner/repo",
            opened_at=ts,
        )
        assert payload.session_id == sid
        assert payload.pr_number == 42
        assert payload.pr_url == "https://github.com/owner/repo/pull/42"
        assert payload.pr_repository == "owner/repo"
        assert payload.opened_at == ts

    def test_round_trip_json(self) -> None:
        """SessionPrOpenedPayload survives JSON round-trip."""
        original = SessionPrOpenedPayload(
            session_id=UUID("12345678-1234-5678-1234-567812345678"),
            pr_number=42,
            pr_url="https://github.com/o/r/pull/42",
            pr_repository="o/r",
            opened_at=datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC),
        )
        restored = SessionPrOpenedPayload.model_validate_json(original.model_dump_json())
        assert restored == original

    def test_missing_field_rejected(self) -> None:
        """Missing pr_number raises ValidationError."""
        with pytest.raises(PydanticValidationError):
            SessionPrOpenedPayload.model_validate(
                {
                    "session_id": "12345678-1234-5678-1234-567812345678",
                    "pr_url": "https://x",
                    "pr_repository": "o/r",
                    "opened_at": "2026-05-01T12:00:00Z",
                }
            )


class TestUsageReportPayload:
    """Tests for UsageReportPayload model."""

    def test_create(self) -> None:
        """UsageReportPayload constructs with all fields."""
        payload = UsageReportPayload(
            five_hour_pct=42,
            seven_day_pct=18,
            five_hour_resets_at=1_777_000_000,
            seven_day_resets_at=1_777_500_000,
            reported_at=1_776_999_000,
        )
        assert payload.five_hour_pct == 42
        assert payload.seven_day_pct == 18
        assert payload.five_hour_resets_at == 1_777_000_000
        assert payload.seven_day_resets_at == 1_777_500_000
        assert payload.reported_at == 1_776_999_000

    def test_overage_above_100_allowed(self) -> None:
        """UsageReportPayload allows pct > 100 (overage)."""
        payload = UsageReportPayload(
            five_hour_pct=137,
            seven_day_pct=42,
            five_hour_resets_at=1,
            seven_day_resets_at=2,
            reported_at=0,
        )
        assert payload.five_hour_pct == 137

    def test_round_trip_json(self) -> None:
        """UsageReportPayload survives JSON round-trip."""
        original = UsageReportPayload(
            five_hour_pct=42,
            seven_day_pct=18,
            five_hour_resets_at=1_777_000_000,
            seven_day_resets_at=1_777_500_000,
            reported_at=1_776_999_000,
        )
        restored = UsageReportPayload.model_validate_json(original.model_dump_json())
        assert restored == original

    def test_missing_field_rejected(self) -> None:
        """Missing reported_at raises ValidationError."""
        with pytest.raises(PydanticValidationError):
            UsageReportPayload.model_validate(
                {
                    "five_hour_pct": 42,
                    "seven_day_pct": 18,
                    "five_hour_resets_at": 1,
                    "seven_day_resets_at": 2,
                }
            )

    def test_is_frozen(self) -> None:
        """UsageReportPayload is immutable."""
        payload = UsageReportPayload(
            five_hour_pct=42,
            seven_day_pct=18,
            five_hour_resets_at=1,
            seven_day_resets_at=2,
            reported_at=0,
        )
        with pytest.raises(PydanticValidationError):
            payload.five_hour_pct = 99  # type: ignore[misc]


class TestAgentTeamsEnvelope:
    """Confirm new payloads can ride on the WebSocketMessage envelope."""

    def test_session_init_in_envelope(self) -> None:
        """SessionInitPayload serializes inside WebSocketMessage.content."""
        payload = SessionInitPayload(
            session_id="abc",
            model="claude-opus-4-7",
            permission_mode="acceptEdits",
            api_key_source="subscription",
            cwd="/x",
            agent_teams_enabled=True,
            initialized_at=datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC),
        )
        msg = WebSocketMessage(
            type=MessageType.SESSION_INIT,
            content=payload.model_dump(mode="json"),
        )
        assert msg.type == MessageType.SESSION_INIT
        data = msg.model_dump(mode="json")
        assert data["type"] == "session.init"
        assert isinstance(data["content"], dict)
        assert data["content"]["session_id"] == "abc"

    def test_usage_report_in_envelope(self) -> None:
        """UsageReportPayload serializes inside WebSocketMessage.content."""
        payload = UsageReportPayload(
            five_hour_pct=42,
            seven_day_pct=18,
            five_hour_resets_at=1,
            seven_day_resets_at=2,
            reported_at=0,
        )
        msg = WebSocketMessage(
            type=MessageType.USAGE_REPORT,
            content=payload.model_dump(mode="json"),
        )
        assert msg.type == MessageType.USAGE_REPORT
        data = msg.model_dump(mode="json")
        assert data["type"] == "usage.report"
        assert isinstance(data["content"], dict)
        assert data["content"]["five_hour_pct"] == 42
