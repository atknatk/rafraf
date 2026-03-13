"""Proactive notification REST endpoints."""

from typing import Annotated
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.proactive_notification import (
    MarkAllReadResponse,
    ProactiveNotificationListResponse,
    ProactiveNotificationResponse,
    UnreadCountResponse,
)
from app.services.proactive_notification_service import ProactiveNotificationService

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

router = APIRouter(
    prefix="/api/v1/proactive-notifications",
    tags=["proactive-notifications"],
)


@router.get(
    "",
    response_model=ProactiveNotificationListResponse,
)
async def list_proactive_notifications(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    priority: Annotated[str | None, Query()] = None,
    is_read: Annotated[bool | None, Query()] = None,
    type: Annotated[str | None, Query(alias="type")] = None,  # noqa: A002
) -> ProactiveNotificationListResponse:
    """List proactive notifications for the authenticated user.

    Supports pagination and optional filters by priority, read status, and type.
    """
    service = ProactiveNotificationService(session)
    return await service.get_notifications(
        user_id=current_user.id,
        page=page,
        page_size=page_size,
        priority=priority,
        is_read=is_read,
        notification_type=type,
    )


@router.patch(
    "/{notification_id}/read",
    response_model=ProactiveNotificationResponse,
)
async def mark_notification_read(
    notification_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ProactiveNotificationResponse:
    """Mark a single proactive notification as read."""
    service = ProactiveNotificationService(session)
    result = await service.mark_read(notification_id, current_user.id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bildirim bulunamadi",
        )
    return result


@router.post(
    "/read-all",
    response_model=MarkAllReadResponse,
)
async def mark_all_notifications_read(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> MarkAllReadResponse:
    """Mark all proactive notifications as read for the authenticated user."""
    service = ProactiveNotificationService(session)
    return await service.mark_all_read(current_user.id)


@router.delete(
    "/{notification_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_proactive_notification(
    notification_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Delete a proactive notification."""
    service = ProactiveNotificationService(session)
    deleted = await service.delete_notification(notification_id, current_user.id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bildirim bulunamadi",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/unread-count",
    response_model=UnreadCountResponse,
)
async def get_unread_count(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> UnreadCountResponse:
    """Get the unread proactive notification count for the authenticated user."""
    service = ProactiveNotificationService(session)
    return await service.get_unread_count(current_user.id)
