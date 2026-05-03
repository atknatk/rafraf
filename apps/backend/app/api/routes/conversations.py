"""REST endpoint — konusma gecmisi sorgusu."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.conversation import (
    ConversationHistoryResponse,
    MessageRatingRequest,
    MessageResponse,
)
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
        Query(description="Sayfalama imleci (en eski mesajin created_at ISO tarihi)"),
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


@router.patch("/{message_id}/rating", response_model=MessageResponse)
async def rate_message(
    message_id: str,
    body: MessageRatingRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> MessageResponse:
    """AI yaniti icin thumbs up/down degerlendirmesi kaydeder."""
    svc = ConversationService(session)
    msg = await svc.rate_message(
        message_id=message_id,
        user_id=str(current_user.id),
        body=body,
    )
    if msg is None:
        raise HTTPException(status_code=404, detail="Message not found")
    return MessageResponse(
        id=msg.id,
        session_id=msg.session_id,
        user_id=msg.user_id,
        project_id=msg.project_id,
        agent_id=msg.agent_id,
        role=msg.role,
        content=msg.content,
        model_used=msg.model_used,
        tokens_used=msg.tokens_used,
        created_at=msg.created_at.isoformat(),
        rating=msg.rating,
        rating_note=msg.rating_note,
        rated_at=msg.rated_at.isoformat() if msg.rated_at else None,
    )


@router.get("/export")
async def export_conversation(
    session: Annotated[AsyncSession, Depends(get_db)],
    project_id: Annotated[
        uuid.UUID | None,
        Query(description="Proje ID'si"),
    ] = None,
    session_id: Annotated[
        str | None,
        Query(description="Oturum ID'si"),
    ] = None,
) -> PlainTextResponse:
    """Konusmayi markdown formatinda disa aktar."""
    svc = ConversationService(session)
    content = await svc.export_conversation(
        project_id=project_id,
        session_id=session_id,
    )
    filename = f"rafraf-export-{datetime.now(tz=UTC).strftime('%Y%m%d-%H%M%S')}.md"
    return PlainTextResponse(
        content=content,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/search")
async def search_messages(
    q: Annotated[str, Query(description="Arama metni")],
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    project_id: Annotated[
        str | None,
        Query(description="Proje ID'si (opsiyonel filtre)"),
    ] = None,
    limit: Annotated[
        int,
        Query(ge=1, le=50, description="Maksimum sonuc sayisi"),
    ] = 20,
) -> list[MessageResponse]:
    """Mesajlarda tam metin arama."""
    svc = ConversationService(session)
    messages = await svc.search_messages(
        user_id=str(current_user.id),
        query=q,
        project_id=project_id,
        limit=min(limit, 50),
    )
    return [
        MessageResponse(
            id=m.id,
            session_id=m.session_id,
            user_id=m.user_id,
            project_id=m.project_id,
            agent_id=m.agent_id,
            role=m.role,
            content=m.content,
            model_used=m.model_used,
            tokens_used=m.tokens_used,
            created_at=m.created_at.isoformat(),
            rating=m.rating,
            rating_note=m.rating_note,
            rated_at=m.rated_at.isoformat() if m.rated_at else None,
        )
        for m in messages
    ]


@router.get("/recent", response_model=ConversationHistoryResponse)
async def get_recent_messages(
    session: Annotated[AsyncSession, Depends(get_db)],
    limit: Annotated[
        int,
        Query(ge=1, le=20, description="Donmesi istenen mesaj sayisi"),
    ] = 1,
) -> ConversationHistoryResponse:
    """En son N mesaji dondurur (tum sessionlar arasinda).

    Home ekraninda "son sohbet" preview kartini beslemek icin kullanilir.
    """
    svc = ConversationService(session)
    return await svc.get_recent_messages(limit=limit)


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
