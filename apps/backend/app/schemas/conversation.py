"""Konusma gecmisi Pydantic schemalar."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field


class MessageRatingRequest(BaseModel, frozen=True):
    """PATCH /{message_id}/rating istek govdesi."""

    rating: Literal["up", "down"]
    note: str | None = Field(None, max_length=500)


class MessageResponse(BaseModel):
    """Tek mesaj yaniti."""

    id: uuid.UUID
    session_id: str
    user_id: str
    project_id: uuid.UUID | None = None
    agent_id: str | None = None
    role: str
    content: str
    model_used: str | None = None
    tokens_used: int | None = None
    created_at: str
    rating: str | None = None
    rating_note: str | None = None
    rated_at: str | None = None


class ConversationHistoryResponse(BaseModel):
    """GET /conversations/history yaniti."""

    messages: list[MessageResponse]
    total: int
    has_more: bool
    next_cursor: str | None = None
