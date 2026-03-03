"""Pydantic request/response schemas for personal memory (mem0 + pgvector)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# --- Domain entities (frozen) ---


class UserProfile(BaseModel):
    """Immutable user profile built from personal memories."""

    model_config = ConfigDict(frozen=True)

    user_id: str
    preferences: dict[str, object]
    habits: list[str]
    total_memories: int
    last_updated: datetime | None


class PersonalMemoryStatsResponse(BaseModel):
    """Statistics about a user's personal memory."""

    model_config = ConfigDict(frozen=True)

    user_id: str
    total_memories: int
    oldest_memory_date: datetime | None
    newest_memory_date: datetime | None


class BulkDeleteResponse(BaseModel):
    """Response for bulk deletion of personal memories."""

    model_config = ConfigDict(frozen=True)

    deleted_count: int
    user_id: str


# --- Request schemas ---


class UserProfileUpdateRequest(BaseModel):
    """Request to update user profile preferences and habits."""

    preferences: dict[str, object] | None = None
    habits: list[str] | None = None


class PersonalFactExtractionRequest(BaseModel):
    """Request for personal fact extraction from conversation messages."""

    messages: list[dict[str, str]] = Field(min_length=1)


class PersonalMemoryUpdateRequest(BaseModel):
    """Request to update a single personal memory."""

    data: str = Field(min_length=1, max_length=4096)


# --- Response schemas ---


class PersonalFactExtractionResponse(BaseModel):
    """Response for personal fact extraction."""

    model_config = ConfigDict(frozen=True)

    extracted_memories: list[str]
    total: int
