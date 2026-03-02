"""Authentication REST endpoints."""

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.auth import RefreshRequest, TokenRequest, TokenResponse
from app.services.auth_service import AuthService

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/token", response_model=TokenResponse)
async def login(
    request: TokenRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    """Authenticate user and return JWT tokens.

    Returns access_token (15min) and refresh_token (7 days).
    """
    service = AuthService(session)
    return await service.authenticate(
        email=request.email,
        password=request.password,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: RefreshRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    """Refresh JWT tokens using a valid refresh token.

    Returns new access_token and refresh_token (token rotation).
    """
    service = AuthService(session)
    return await service.refresh_tokens(refresh_token_str=request.refresh_token)
