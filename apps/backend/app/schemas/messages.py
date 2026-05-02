"""WebSocket message schemas (Pydantic v2)."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class MessageDirection(StrEnum):
    """Direction of a WebSocket message."""

    CLIENT_TO_SERVER = "client_to_server"
    SERVER_TO_CLIENT = "server_to_client"


class MessageType(StrEnum):
    """Supported WebSocket message types."""

    TEXT = "text"
    CONNECTION_ACK = "connection_ack"
    ERROR = "error"
    PROGRESS = "progress"
    PING = "ping"
    PONG = "pong"
    ACTION_RESULT = "action_result"
    QUESTION = "question"
    STATUS = "status"
    APPROVAL_RESPONSE = "approval_response"
    # Streaming response types
    CHAT_STREAM = "chat.stream"
    CHAT_STREAM_END = "chat.stream_end"
    # Code diff type
    CODE_DIFF = "code.diff"
    # Proactive suggestion type
    SUGGESTION = "suggestion"
    # Typing indicators (server → client)
    TYPING_START = "typing.start"
    TYPING_END = "typing.end"
    # Stream control (client → server)
    CANCEL_STREAM = "stream.cancel"
    # Stream cancelled ack (server → client)
    STREAM_CANCELLED = "stream.cancelled"
    # Task status updates (server → client)
    TASK_STATUS = "task_status"
    # Claude Agent Teams events (server → client, sourced from bridge stream-json)
    SESSION_INIT = "session.init"
    SUBAGENT_SPAWNED = "subagent.spawned"
    SUBAGENT_PROGRESS = "subagent.progress"
    SUBAGENT_COMPLETED = "subagent.completed"
    RATE_LIMIT_INFO = "rate_limit.info"
    SESSION_TITLE = "session.title"
    SESSION_PR_OPENED = "session.pr_opened"
    USAGE_REPORT = "usage.report"


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


class ProgressStepPayload(BaseModel):
    """Single step info in a detailed progress message."""

    model_config = ConfigDict(frozen=True)

    id: str
    step_type: str
    label: str
    status: str
    tool_name: str | None = None
    duration_seconds: float | None = None
    detail: str | None = None


class ProgressPayload(BaseModel):
    """Payload for progress update messages."""

    model_config = ConfigDict(frozen=True)

    task: str
    step: int
    total_steps: int
    percentage: int
    details: str | None = None
    phase: str | None = None
    steps_detail: list[ProgressStepPayload] | None = None


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


class ChatStreamPayload(BaseModel):
    """Payload for streaming text delta messages."""

    model_config = ConfigDict(frozen=True)

    message_id: str
    delta: str
    index: int


class ChatStreamEndPayload(BaseModel):
    """Payload for stream completion messages."""

    model_config = ConfigDict(frozen=True)

    message_id: str
    full_text: str
    model_used: str
    tokens_used: dict[str, int]


class CodeDiffLinePayload(BaseModel):
    """Bir diff satiri."""

    model_config = ConfigDict(frozen=True)

    type: str  # "added", "removed", "context"
    content: str
    line_number_old: int | None = None
    line_number_new: int | None = None


class CodeDiffFilePayload(BaseModel):
    """Bir dosyanin diff'i."""

    model_config = ConfigDict(frozen=True)

    file_path: str
    is_new_file: bool = False
    is_deleted: bool = False
    additions: int = 0
    deletions: int = 0
    lines: list[CodeDiffLinePayload]


class CodeDiffPayload(BaseModel):
    """Code diff mesaj payload'i."""

    model_config = ConfigDict(frozen=True)

    project_path: str
    total_additions: int
    total_deletions: int
    files_changed: int
    files: list[CodeDiffFilePayload]


class SuggestionPayload(BaseModel):
    """Proaktif takip onerileri payload."""

    model_config = ConfigDict(frozen=True)

    message_id: str  # Ilgili AI mesajinin ID'si
    suggestions: list[str]  # ["Testleri calistir", "PR olustur", ...]


# ---------------------------------------------------------------------------
# Claude Agent Teams payloads (T1.5)
#
# These payloads carry events that originate from the Mac Go bridge's
# stream-json parser (claude CLI subprocess with
# CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1) and are forwarded to the iOS
# client over WebSocket. See docs/10_Production_Pivot_Spec.md §6.4 and
# docs/11_Bridge_Spec.md §6 for the source events.
# ---------------------------------------------------------------------------


class SessionInitPayload(BaseModel):
    """Payload for `session.init` — emitted on `system/init` stream event."""

    model_config = ConfigDict(frozen=True)

    session_id: str
    model: str
    permission_mode: str
    api_key_source: str
    cwd: str
    agent_teams_enabled: bool
    initialized_at: datetime


class SubagentSpawnedPayload(BaseModel):
    """Payload for `subagent.spawned` — emitted on `system/task_started`."""

    model_config = ConfigDict(frozen=True)

    task_id: str
    name: str
    description: str | None = None
    prompt_preview: str
    subagent_type: str | None = None
    isolation: str | None = None  # "worktree" or None
    started_at: datetime


class SubagentProgressPayload(BaseModel):
    """Payload for `subagent.progress` — emitted on `system/task_progress`."""

    model_config = ConfigDict(frozen=True)

    task_id: str
    status: str  # "in_progress", "queued"
    activity: str  # short label e.g. "Editing config.toml"
    updated_at: datetime


class SubagentCompletedPayload(BaseModel):
    """Payload for `subagent.completed` — emitted on `system/task_notification`."""

    model_config = ConfigDict(frozen=True)

    task_id: str
    status: str  # "completed", "failed"
    summary: str | None = None
    total_tokens: int
    tool_uses: int
    duration_ms: int
    completed_at: datetime


class RateLimitInfoPayload(BaseModel):
    """Payload for `rate_limit.info` — emitted on `rate_limit_event`."""

    model_config = ConfigDict(frozen=True)

    status: str  # "allowed", "limited"
    rate_limit_type: str  # "five_hour"
    resets_at: int  # unix timestamp (seconds)
    overage_status: str
    is_using_overage: bool


class SessionTitlePayload(BaseModel):
    """Payload for `session.title` — emitted by storage watcher (`ai-title`)."""

    model_config = ConfigDict(frozen=True)

    session_id: UUID
    ai_title: str
    generated_at: datetime


class SessionPrOpenedPayload(BaseModel):
    """Payload for `session.pr_opened` — emitted by storage watcher (`pr-link`)."""

    model_config = ConfigDict(frozen=True)

    session_id: UUID
    pr_number: int
    pr_url: str
    pr_repository: str
    opened_at: datetime


class UsageReportPayload(BaseModel):
    """Payload for `usage.report` — 5h + 7d Claude Code subscription usage.

    Source: `~/.claude/usage.json` written by Mac statusline.py and tailed
    by the bridge's statusline watcher (see docs/10 §2.11 + §6.4).
    """

    model_config = ConfigDict(frozen=True)

    five_hour_pct: int  # 0–100+ (overage durumunda 100'u asabilir)
    seven_day_pct: int
    five_hour_resets_at: int  # unix timestamp (seconds)
    seven_day_resets_at: int
    reported_at: int  # usage.json yazilma zamani (stale detection icin)
