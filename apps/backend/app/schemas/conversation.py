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
    """GET /conversations/history (and /conversations/messages-since) yaniti.

    Pagination contract:
    - ``has_more=True`` means more rows exist beyond the returned page.
    - ``next_cursor`` is the ISO 8601 ``created_at`` of the LAST returned
      message; pass it back as ``since`` (for messages-since) or as
      ``cursor`` (for history) to fetch the subsequent page.
    - ``next_cursor`` is ``None`` whenever ``has_more=False``.

    The field is named ``next_cursor`` for backwards compatibility with the
    existing iOS history-fetch code; the messages-since spec also refers
    to it as ``next_since``.
    """

    messages: list[MessageResponse]
    total: int
    has_more: bool
    next_cursor: str | None = None
