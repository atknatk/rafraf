"""WebSocket message schemas (Pydantic v2)."""

from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class MessageDirection(StrEnum):
    """Direction of a WebSocket message."""

    CLIENT_TO_SERVER = "client_to_server"
    SERVER_TO_CLIENT = "server_to_client"


class MessageType(StrEnum):
    """Supported WebSocket message types."""

    TEXT = "text"
    VOICE = "voice"
    CONNECTION_ACK = "connection_ack"
    ERROR = "error"
    PROGRESS = "progress"
    PING = "ping"
    PONG = "pong"
    ACTION_RESULT = "action_result"
    QUESTION = "question"
    STATUS = "status"
    APPROVAL_RESPONSE = "approval_response"


class MessageAttachment(BaseModel):
    """Attachment within a WebSocket message."""

    model_config = ConfigDict(frozen=True)

    type: str
    url: str
    mime_type: str
    size_bytes: int


class MessageMetadata(BaseModel):
    """Metadata for a WebSocket message."""

    model_config = ConfigDict(frozen=True)

    timestamp: str
    session_id: str | None = None
    project_id: str | None = None
    message_id: str | None = None
    direction: MessageDirection


class WebSocketMessage(BaseModel):
    """Base WebSocket message schema."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    type: MessageType
    content: str | dict[str, object] | None = None
    metadata: MessageMetadata | None = None
    attachments: list[MessageAttachment] | None = None


class ConnectionAckPayload(BaseModel):
    """Payload sent when a client successfully connects."""

    model_config = ConfigDict(frozen=True)

    user_id: str
    session_id: str
    server_time: str


class ErrorPayload(BaseModel):
    """Payload for error messages."""

    model_config = ConfigDict(frozen=True)

    error_code: str
    message: str
    details: str | None = None
    suggestion: str | None = None
    recoverable: bool = True


class ProgressPayload(BaseModel):
    """Payload for progress update messages."""

    model_config = ConfigDict(frozen=True)

    task: str
    step: int
    total_steps: int
    percentage: int
    details: str | None = None


class PingPongPayload(BaseModel):
    """Payload for heartbeat ping/pong messages."""

    model_config = ConfigDict(frozen=True)

    timestamp: str


class ActionResultPayload(BaseModel):
    """Payload for tool action result messages."""

    model_config = ConfigDict(frozen=True)

    tool: str
    action: str
    success: bool
    output: str
    duration_seconds: float | None = None
    details: dict[str, object] | None = None


class QuestionOptionPayload(BaseModel):
    """A single option in a question message."""

    model_config = ConfigDict(frozen=True)

    id: str
    label: str
    style: str


class QuestionPayload(BaseModel):
    """Payload for approval question messages."""

    model_config = ConfigDict(frozen=True)

    approval_id: str
    question: str
    context: str | None = None
    options: list[QuestionOptionPayload]
    timeout_seconds: int
    category: str


class StatusPayload(BaseModel):
    """Payload for project status messages."""

    model_config = ConfigDict(frozen=True)

    project_id: str
    project_name: str
    overall_status: str
    details: dict[str, object] | None = None


class ApprovalResponsePayload(BaseModel):
    """Payload for client approval response messages."""

    model_config = ConfigDict(frozen=True)

    approval_id: str
    decision: str
    note: str | None = None
