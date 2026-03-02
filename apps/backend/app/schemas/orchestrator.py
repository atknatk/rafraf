"""Orchestrator Pydantic schemas for request/response models."""

from pydantic import BaseModel, ConfigDict


class ToolCall(BaseModel):
    """Represents a tool call from Claude."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    input: dict[str, object]


class ToolResult(BaseModel):
    """Result of a tool execution."""

    model_config = ConfigDict(frozen=True)

    tool_use_id: str
    content: str
    is_error: bool = False


class OrchestratorRequest(BaseModel):
    """Request to the orchestrator for processing a user message."""

    model_config = ConfigDict(frozen=True)

    session_id: str
    user_id: str
    message: str
    project_id: str | None = None


class OrchestratorResponse(BaseModel):
    """Response from the orchestrator after processing."""

    model_config = ConfigDict(frozen=True)

    session_id: str
    response_text: str
    model_used: str
    tokens_input: int
    tokens_output: int
    tool_calls_count: int


class ApprovalRequest(BaseModel):
    """Request for user approval before executing a tool."""

    model_config = ConfigDict(frozen=True)

    approval_id: str
    tool_name: str
    action: str
    description: str
    category: str
    timeout_seconds: int = 300


class ApprovalResponse(BaseModel):
    """User response to an approval request."""

    model_config = ConfigDict(frozen=True)

    approval_id: str
    decision: str
    note: str | None = None
