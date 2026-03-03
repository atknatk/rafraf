"""Push notification REST endpoints."""

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.notifications import (
    DeviceTokenDeleteRequest,
    DeviceTokenRegisterRequest,
    DeviceTokenRegisterResponse,
    NotificationSettingsResponse,
    NotificationSettingsUpdateRequest,
)
from app.services.notification_service import NotificationService

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


@router.post(
    "/device-token",
    response_model=DeviceTokenRegisterResponse,
    status_code=status.HTTP_200_OK,
)
async def register_device_token(
    request: DeviceTokenRegisterRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> DeviceTokenRegisterResponse:
    """Register an APNs device token for the authenticated user.

    Upserts — the same token is reactivated if previously deactivated.
    """
    service = NotificationService(session)
    return await service.register_token(
        user_id=current_user.id,
        token=request.token,
        platform=request.platform,
        app_version=request.app_version,
    )


@router.delete(
    "/device-token",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_device_token(
    request: DeviceTokenDeleteRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Deactivate a device token (e.g. on user logout)."""
    service = NotificationService(session)
    await service.deactivate_token(
        user_id=current_user.id,
        token=request.token,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/settings",
    response_model=NotificationSettingsResponse,
)
async def get_notification_settings(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> NotificationSettingsResponse:
    """Return the current notification preferences for the user."""
    service = NotificationService(session)
    return await service.get_settings(user_id=current_user.id)


@router.patch(
    "/settings",
    response_model=NotificationSettingsResponse,
)
async def update_notification_settings(
    request: NotificationSettingsUpdateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> NotificationSettingsResponse:
    """Partially update notification preferences."""
    service = NotificationService(session)
    return await service.update_settings(
        user_id=current_user.id,
        payload=request,
    )
