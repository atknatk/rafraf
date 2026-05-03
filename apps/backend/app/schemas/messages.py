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
    # V1.x WS reliability ack envelope (server → client). Echoes
    # metadata.client_message_id so iOS can stop its half-dead-socket retry
    # loop. See shared/api-contracts/ws/ack-messages.json.
    ACK = "ack"
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
    # V1.x Claude Subprocess Supervisor (Item 11) — bridge → backend → iOS.
    # Mirrors the Go bridge envelope types in
    # ``apps/rafraf-bridge/internal/protocol/messages.go``. See
    # ``shared/feature-specs/V1x-claude-supervisor.md`` §4 for the wire shape
    # contract that all three layers must agree on.
    CLAUDE_PROCESS_SPAWNED = "event.claude.process.spawned"
    CLAUDE_PROCESS_HEALTHCHECK = "event.claude.process.healthcheck"
    CLAUDE_PROCESS_STALLED = "event.claude.process.stalled"
    CLAUDE_PROCESS_CRASHED = "event.claude.process.crashed"
    CLAUDE_PROCESS_RECOVERED = "event.claude.process.recovered"
    CLAUDE_PROCESS_DIAGNOSED = "event.claude.process.diagnosed"
    # V1.x Claude Subprocess Supervisor — iOS → backend → bridge.
    CLAUDE_PROCESS_RETRY = "command.claude.process.retry"


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


# ---------------------------------------------------------------------------
# Claude Subprocess Supervisor payloads (V1.x — Item 11)
#
# Wire-shape contract:
#   - All snake_case keys on the wire (matches the Go bridge JSON marshal).
#   - All payloads ``frozen=True`` (immutable per project rules).
#   - ``populate_by_name=True`` (defensive — accept the snake_case form even
#     when the iOS DTOs round-trip through camelCase via aliases).
#
# Source-of-truth field list lives in
# ``shared/feature-specs/V1x-claude-supervisor.md`` §4. Bridge protocol structs
# in ``apps/rafraf-bridge/internal/protocol/messages.go`` MUST match these
# field-for-field (drift guard:
# ``shared/api-contracts/ws/claude-process-messages.json``).
# ---------------------------------------------------------------------------


class ClaudeProcessSpawnedPayload(BaseModel):
    """Payload for `event.claude.process.spawned` (§4.1)."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    session_id: str
    pid: int = Field(gt=0)
    started_at: datetime
    model: str
    args: list[str]
    permission_mode: str
    project_dir: str


class ClaudeProcessHealthcheckPayload(BaseModel):
    """Payload for `event.claude.process.healthcheck` (§4.2).

    `status` ∈ {starting, running, idle, stale, rate_limited, completed}.
    """

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    session_id: str
    pid: int = Field(gt=0)
    status: str
    last_stdout_age_ms: int
    current_tokens: int
    memory_rss_kb: int
    cpu_percent_1s: float
    observed_at: datetime


class ClaudeProcessStalledPayload(BaseModel):
    """Payload for `event.claude.process.stalled` (§4.3)."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    session_id: str
    pid: int = Field(gt=0)
    last_activity_at: datetime
    stale_for_ms: int
    stderr_tail: str  # bridge caps at 8 KiB
    stderr_tail_truncated: bool
    self_heal_pending: bool


class ClaudeProcessCrashedPayload(BaseModel):
    """Payload for `event.claude.process.crashed` (§4.4)."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    session_id: str
    pid: int = Field(gt=0)
    exit_code: int
    signal: str  # "" when exit was clean-but-nonzero
    stderr_tail: str
    duration_ms: int
    crashed_at: datetime


class ClaudeProcessRecoveredPayload(BaseModel):
    """Payload for `event.claude.process.recovered` (§4.5).

    `recovery_reason` ∈ {diagnostic_recommended_wait, rate_limit_window_expired,
    manual_retry, stdout_resumed}. `old_session_id == new_session_id` on
    self-recovery; differs only on a manual retry that issues a new run.
    """

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    old_session_id: str
    new_session_id: str
    recovery_reason: str
    recovered_at: datetime


class ClaudeProcessDiagnosedPayload(BaseModel):
    """Payload for `event.claude.process.diagnosed` (§4.6).

    `recommended_action` ∈ {retry, wait, manual}. `diagnosis_text` capped at
    4 KiB by the bridge. `diagnostic_tokens_used` ≤ 500 (cost guard).
    """

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    session_id: str
    diagnosis_text: str  # bridge caps at 4 KiB
    recommended_action: str
    diagnostic_tokens_used: int
    diagnostic_duration_ms: int
    diagnosed_at: datetime


class ClaudeProcessRetryCommand(BaseModel):
    """Payload for `command.claude.process.retry` (§4.7) — iOS → backend.

    `user_id` is iOS-supplied for traceability but the backend's `websocket.py`
    handler MUST cross-check it against the JWT-authenticated `user_id` of the
    connection before forwarding to the bridge (no impersonation).
    """

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    session_id: str
    user_id: str
