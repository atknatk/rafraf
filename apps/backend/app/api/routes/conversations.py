"""REST endpoint — konusma gecmisi sorgusu."""

from __future__ import annotations

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.conversation import ConversationHistoryResponse
from app.services.conversation_service import ConversationService

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])


@router.get("/history", response_model=ConversationHistoryResponse)
async def get_conversation_history(
    session: Annotated[AsyncSession, Depends(get_db)],
    project_id: Annotated[
        uuid.UUID | None,
        Query(description="Proje ID'si (proje bazli sorgu)"),
    ] = None,
    session_id: Annotated[
        str | None,
        Query(description="Oturum ID'si (session bazli sorgu)"),
    ] = None,
    limit: Annotated[
        int,
        Query(ge=1, le=200, description="Sayfa basina mesaj sayisi"),
    ] = 50,
    cursor: Annotated[
        str | None,
        Query(description="Sayfalama imleci (onceki sayfanin en eski mesajinin created_at ISO tarihi)"),
    ] = None,
) -> ConversationHistoryResponse:
    """Proje veya session bazinda mesaj gecmisini dondurur.

    En az bir parametre (project_id veya session_id) gereklidir.
    """
    svc = ConversationService(session)
    return await svc.get_history(
        project_id=project_id,
        session_id=session_id,
        limit=limit,
        cursor=cursor,
    )


@router.get("/missed", response_model=ConversationHistoryResponse)
async def get_missed_messages(
    session: Annotated[AsyncSession, Depends(get_db)],
    since: Annotated[
        str,
        Query(description="ISO 8601 timestamp — bu zamandan sonraki mesajlari getir"),
    ],
    project_id: Annotated[
        uuid.UUID | None,
        Query(description="Proje ID'si (proje bazli sorgu)"),
    ] = None,
    session_id: Annotated[
        str | None,
        Query(description="Oturum ID'si (session bazli sorgu)"),
    ] = None,
) -> ConversationHistoryResponse:
    """Return messages created after the given timestamp.

    Used by iOS client on reconnect to fetch missed messages.
    """
    svc = ConversationService(session)
    return await svc.get_messages_since(
        since=since,
        project_id=project_id,
        session_id=session_id,
    )
