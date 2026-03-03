"""REST endpoints for conversation memory (session management)."""

from typing import Annotated

import structlog
from fastapi import APIRouter, Query
from starlette import status

from app.core.exceptions import ConflictError, NotFoundError
from app.schemas.conversation_memory import (
    ContextWindowUsage,
    ConversationContextResponse,
    ConversationCreateRequest,
    ConversationMessageCreateRequest,
    ConversationMessageResponse,
    ConversationMessagesResponse,
    ConversationSessionResponse,
    ConversationSummaryResponse,
)
from app.services.conversation_memory_service import (
    SessionEndedError,
    SessionNotFoundError,
    conversation_memory_service,
)

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])


@router.post(
    "",
    response_model=ConversationSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_session(
    body: ConversationCreateRequest,
) -> ConversationSessionResponse:
    """Create a new conversation session."""
    session = await conversation_memory_service.create_session(
        user_id=body.user_id,
        project_id=body.project_id,
        ttl_seconds=body.ttl_seconds,
    )
    return ConversationSessionResponse(
        session_id=session.session_id,
        user_id=session.user_id,
        project_id=session.project_id,
        status=session.status,
        message_count=session.message_count,
        total_tokens=session.total_tokens,
        created_at=session.created_at,
        last_activity_at=session.last_activity_at,
        summary=session.summary,
    )


@router.get(
    "/{session_id}",
    response_model=ConversationSessionResponse,
)
async def get_session(
    session_id: str,
) -> ConversationSessionResponse:
    """Get session information."""
    try:
        session = await conversation_memory_service.get_session(session_id)
    except SessionNotFoundError as exc:
        raise NotFoundError(message=str(exc)) from exc
    return ConversationSessionResponse(
        session_id=session.session_id,
        user_id=session.user_id,
        project_id=session.project_id,
        status=session.status,
        message_count=session.message_count,
        total_tokens=session.total_tokens,
        created_at=session.created_at,
        last_activity_at=session.last_activity_at,
        summary=session.summary,
    )


@router.delete(
    "/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def end_session(
    session_id: str,
) -> None:
    """End a conversation session (creates summary, cleans up)."""
    try:
        await conversation_memory_service.end_session(session_id)
    except SessionNotFoundError as exc:
        raise NotFoundError(message=str(exc)) from exc


@router.get(
    "/{session_id}/messages",
    response_model=ConversationMessagesResponse,
)
async def get_messages(
    session_id: str,
    limit: Annotated[
        int,
        Query(ge=1, le=200, description="Maksimum mesaj sayisi"),
    ] = 50,
    offset: Annotated[
        int,
        Query(ge=0, description="Baslangic pozisyonu"),
    ] = 0,
) -> ConversationMessagesResponse:
    """Get message history for a session."""
    try:
        messages, total, has_more = await conversation_memory_service.get_messages(
            session_id=session_id,
            limit=limit,
            offset=offset,
        )
    except SessionNotFoundError as exc:
        raise NotFoundError(message=str(exc)) from exc
    return ConversationMessagesResponse(
        messages=[
            ConversationMessageResponse(
                id=msg.id,
                role=msg.role,
                content=msg.content,
                timestamp=msg.timestamp,
                token_count=msg.token_count,
                metadata=msg.metadata,
            )
            for msg in messages
        ],
        total=total,
        has_more=has_more,
    )


@router.post(
    "/{session_id}/messages",
    response_model=ConversationMessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_message(
    session_id: str,
    body: ConversationMessageCreateRequest,
) -> ConversationMessageResponse:
    """Add a message to the conversation."""
    from app.core.config import get_settings

    try:
        message = await conversation_memory_service.add_message(
            session_id=session_id,
            role=body.role,
            content=body.content,
            metadata=body.metadata,
        )
    except SessionNotFoundError as exc:
        raise NotFoundError(message=str(exc)) from exc
    except SessionEndedError as exc:
        raise ConflictError(message=str(exc)) from exc

    # Get updated session for context window usage
    session = await conversation_memory_service.get_session(session_id)
    settings = get_settings()
    max_tokens = settings.conversation_max_tokens
    usage_percent = round((session.total_tokens / max_tokens) * 100, 1) if max_tokens > 0 else 0.0

    return ConversationMessageResponse(
        id=message.id,
        role=message.role,
        content=message.content,
        timestamp=message.timestamp,
        token_count=message.token_count,
        metadata=message.metadata,
        context_window_usage=ContextWindowUsage(
            total_tokens=session.total_tokens,
            max_tokens=max_tokens,
            usage_percent=usage_percent,
        ),
    )


@router.post(
    "/{session_id}/summarize",
    response_model=ConversationSummaryResponse,
)
async def summarize_session(
    session_id: str,
) -> ConversationSummaryResponse:
    """Create a session summary."""
    try:
        return await conversation_memory_service.summarize_session(session_id)
    except SessionNotFoundError as exc:
        raise NotFoundError(message=str(exc)) from exc


@router.get(
    "/{session_id}/context",
    response_model=ConversationContextResponse,
)
async def get_context(
    session_id: str,
    max_tokens: Annotated[
        int | None,
        Query(ge=1000, le=100000, description="Maksimum token limiti"),
    ] = None,
) -> ConversationContextResponse:
    """Get context-window-optimized message history."""
    try:
        return await conversation_memory_service.get_context_window(
            session_id=session_id,
            max_tokens=max_tokens,
        )
    except SessionNotFoundError as exc:
        raise NotFoundError(message=str(exc)) from exc
