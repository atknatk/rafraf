"""Task request/response Pydantic v2 schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TaskCreate(BaseModel):
    """POST /api/v1/tasks request body."""

    title: str = Field(default="", description="Short task description (max 100 chars)")
    prompt: str = Field(..., min_length=1, description="User's task prompt")
    task_type: str = Field(default="feature", description="Task type: feature, bugfix, analysis")
    project_id: uuid.UUID | None = Field(None, description="Optional project ID")


class TaskUpdate(BaseModel):
    """PATCH request body for task updates."""

    current_step: str | None = Field(None, description="Current pipeline step")
    progress_pct: int | None = Field(None, ge=0, le=100, description="Progress percentage")
    completed_steps: int | None = Field(None, ge=0, description="Number of completed steps")


class LiveActivityTokenRequest(BaseModel):
    """PATCH /api/v1/tasks/{id}/live-activity request body."""

    push_token: str = Field(..., min_length=1, description="APNs push token for Live Activity")


class TaskResponse(BaseModel):
    """Task response DTO returned from all task endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="Task unique ID")
    user_id: uuid.UUID = Field(..., description="Owner user ID")
    project_id: uuid.UUID | None = Field(None, description="Associated project ID")
    agent_id: str | None = Field(None, description="Assigned agent host_id")
    title: str = Field(default="", description="Short task description")
    prompt: str = Field(..., description="Original user prompt")
    task_type: str = Field(..., description="Task type")
    status: str = Field(..., description="Current task status")
    current_step: str | None = Field(None, description="Current pipeline step")
    total_steps: int = Field(default=4, description="Total pipeline steps")
    completed_steps: int = Field(default=0, description="Completed pipeline steps")
    progress_pct: int = Field(default=0, description="Progress 0-100")
    result_summary: str | None = Field(None, description="Completion summary")
    error_message: str | None = Field(None, description="Error message if failed")
    claude_session_id: str | None = Field(None, description="Claude session ID")
    claude_task_id: str | None = Field(None, description="Claude task ID")
    has_live_activity_token: bool = Field(default=False, description="Whether APNs token is registered")
    created_at: datetime | str | None = Field(None, description="Creation timestamp")
    started_at: datetime | str | None = Field(None, description="Start timestamp")
    completed_at: datetime | str | None = Field(None, description="Completion timestamp")
    updated_at: datetime | str | None = Field(None, description="Last update timestamp")


class TaskListResponse(BaseModel):
    """GET /api/v1/tasks/history response with pagination."""

    tasks: list[TaskResponse] = Field(default_factory=list, description="Task list")
    total: int = Field(..., ge=0, description="Total task count")
    page: int = Field(..., ge=1, description="Current page number")
    page_size: int = Field(..., ge=1, description="Items per page")
