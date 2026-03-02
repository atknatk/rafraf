"""Pydantic request/response schemas for the memory manager."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# --- Domain entities (frozen) ---


class ProjectMemoryEntity(BaseModel):
    """Immutable project memory domain entity."""

    model_config = ConfigDict(frozen=True)

    id: uuid.UUID
    project_id: uuid.UUID
    category: str
    key: str
    value: dict[str, object]
    confidence: float
    source: str
    last_verified_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PersonalMemoryItem(BaseModel):
    """Single personal memory item returned from mem0."""

    model_config = ConfigDict(frozen=True)

    id: str
    memory: str
    score: float | None = None
    metadata: dict[str, object] | None = None


class MemoryContext(BaseModel):
    """Aggregated memory context for a Claude API call."""

    model_config = ConfigDict(frozen=True)

    personal_memories: list[str]
    project_summary: dict[str, object]
    recent_actions: list[dict[str, object]]
    conversation_summary: str | None = None
    token_count: int = 0


# --- Request schemas ---


class ProjectMemoryCreateRequest(BaseModel):
    """Request to create or update a project memory entry (UPSERT)."""

    category: str = Field(max_length=50)
    key: str = Field(max_length=100)
    value: dict[str, object]
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    source: str = Field(default="user_stated", max_length=50)


# --- Response schemas ---


class ProjectMemoryResponse(BaseModel):
    """Single project memory response."""

    id: uuid.UUID
    project_id: uuid.UUID
    category: str
    key: str
    value: dict[str, object]
    confidence: float
    source: str
    last_verified_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ProjectMemoryListResponse(BaseModel):
    """List response for project memories."""

    items: list[ProjectMemoryResponse]
    total: int


class PersonalMemoryListResponse(BaseModel):
    """List response for personal memories (mem0)."""

    items: list[PersonalMemoryItem]
    total: int


class MemoryContextResponse(BaseModel):
    """Full memory context response for a message."""

    personal_memories: list[str]
    project_summary: dict[str, object]
    conversation_summary: str | None = None
    token_count: int
