"""Pydantic schemas for conversation memory (Redis session management)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# --- Domain entities (frozen) ---


class ConversationMessage(BaseModel):
    """Immutable conversation message entity."""

    model_config = ConfigDict(frozen=True)

    id: str
    role: str  # "user" | "assistant" | "tool" | "system"
    content: str
    timestamp: datetime
    token_count: int
    metadata: dict[str, str] | None = None


class ConversationSession(BaseModel):
    """Immutable conversation session entity."""

    model_config = ConfigDict(frozen=True)

    session_id: str
    user_id: str
    project_id: str | None = None
    status: str  # "active" | "ended" | "summarized"
    message_count: int
    total_tokens: int
    created_at: datetime
    last_activity_at: datetime | None = None
    summary: str | None = None


# --- Request schemas ---


class ConversationCreateRequest(BaseModel):
    """Request to create a new conversation session."""

    user_id: str = Field(min_length=1, max_length=100)
    project_id: str | None = Field(default=None, description="Opsiyonel proje ID")
    ttl_seconds: int | None = Field(
        default=None,
        ge=60,
        le=172800,
        description="Session TTL suresi (saniye). Varsayilan: 86400",
    )


class ConversationMessageCreateRequest(BaseModel):
    """Request to add a message to a conversation."""

    role: str = Field(pattern=r"^(user|assistant|tool|system)$")
    content: str = Field(min_length=1, max_length=100000)
    metadata: dict[str, str] | None = None


# --- Response schemas ---


class ContextWindowUsage(BaseModel):
    """Context window usage info."""

    total_tokens: int
    max_tokens: int
    usage_percent: float


class ConversationSessionResponse(BaseModel):
    """Response for a conversation session."""

    session_id: str
    user_id: str
    project_id: str | None = None
    status: str
    message_count: int
    total_tokens: int
    created_at: datetime
    last_activity_at: datetime | None = None
    summary: str | None = None


class ConversationMessageResponse(BaseModel):
    """Response for a single message."""

    id: str
    role: str
    content: str
    timestamp: datetime
    token_count: int
    metadata: dict[str, str] | None = None
    context_window_usage: ContextWindowUsage | None = None


class ConversationMessagesResponse(BaseModel):
    """Response for message list."""

    messages: list[ConversationMessageResponse]
    total: int
    has_more: bool


class ConversationSummaryResponse(BaseModel):
    """Response for session summary."""

    session_id: str
    summary: str
    original_message_count: int
    original_token_count: int
    summary_token_count: int


class ConversationContextResponse(BaseModel):
    """Response for context window optimized messages."""

    messages: list[dict[str, str]]
    summary: str | None = None
    total_tokens: int
    messages_included: int
    messages_summarized: int
