"""Konusma gecmisi Pydantic schemalar."""

from __future__ import annotations

import uuid

from pydantic import BaseModel


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


class ConversationHistoryResponse(BaseModel):
    """GET /conversations/history yaniti."""

    messages: list[MessageResponse]
    total: int
    has_more: bool
    next_cursor: str | None = None
