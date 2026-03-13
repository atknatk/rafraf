"""Backup/disaster recovery API routes."""

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.backup import (
    BackupListItem,
    BackupListResponse,
    BackupResponse,
    BackupRotationResponse,
    BackupStatusResponse,
    BackupVerifyRequest,
    BackupVerifyResponse,
)
from app.services.backup_service import BackupError, backup_service

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

router = APIRouter(
    prefix="/api/v1/backups",
    tags=["backups"],
)


@router.get("/status", response_model=BackupStatusResponse)
async def get_backup_status(
    _current_user: Annotated[User, Depends(get_current_user)],
) -> BackupStatusResponse:
    """Get overall backup health status.

    Returns latest backup info and health indicators.
    """
    try:
        status = await backup_service.get_backup_status()
        return BackupStatusResponse(
            health=str(status["health"]),
            retention_days=str(status["retention_days"]),
            issues=str(status["issues"]),
            latest_postgres=status["latest_postgres"],  # type: ignore[arg-type]
            latest_redis=status["latest_redis"],  # type: ignore[arg-type]
            recent_backups=status["recent_backups"],  # type: ignore[arg-type]
        )
    except Exception as exc:
        await logger.aexception("backup_status_error")
        raise HTTPException(status_code=500, detail=f"Backup durumu alinamadi: {exc}") from exc


@router.post("/postgres", response_model=BackupResponse)
async def create_postgres_backup(
    _current_user: Annotated[User, Depends(get_current_user)],
) -> BackupResponse:
    """Create a PostgreSQL backup (pg_dump) and upload to S3.

    This endpoint triggers a full database backup using pg_dump --format=custom,
    compresses with gzip, and uploads to S3.
    """
    try:
        result = await backup_service.create_postgres_backup()
        return BackupResponse(**result)
    except BackupError as exc:
        await logger.aexception("backup_postgres_failed", operation=exc.operation)
        raise HTTPException(
            status_code=500,
            detail=f"PostgreSQL backup basarisiz: {exc}",
        ) from exc


@router.post("/redis", response_model=BackupResponse)
async def create_redis_snapshot(
    _current_user: Annotated[User, Depends(get_current_user)],
) -> BackupResponse:
    """Create a Redis RDB snapshot and upload to S3.

    Triggers BGSAVE, waits for completion, then uploads the RDB file.
    """
    try:
        result = await backup_service.create_redis_snapshot()
        return BackupResponse(**result)
    except BackupError as exc:
        await logger.aexception("backup_redis_failed", operation=exc.operation)
        raise HTTPException(
            status_code=500,
            detail=f"Redis snapshot basarisiz: {exc}",
        ) from exc


@router.get("/list", response_model=BackupListResponse)
async def list_backups(
    _current_user: Annotated[User, Depends(get_current_user)],
    backup_type: str = Query(
        default="all",
        description="Backup tipi filtresi (postgres/redis/all)",
    ),
    max_results: int = Query(
        default=50, ge=1, le=200, description="Maksimum sonuc sayisi",
    ),
) -> BackupListResponse:
    """List available backups from S3.

    Supports filtering by backup type and pagination.
    """
    if backup_type not in ("postgres", "redis", "all"):
        raise HTTPException(
            status_code=400,
            detail="Gecersiz backup_type. Gecerli degerler: postgres, redis, all",
        )

    try:
        backups = await backup_service.list_backups(
            backup_type=backup_type,
            max_results=max_results,
        )
        items = [BackupListItem(**b) for b in backups]
        return BackupListResponse(backups=items, total=len(items))
    except Exception as exc:
        await logger.aexception("backup_list_error")
        raise HTTPException(status_code=500, detail=f"Backup listesi alinamadi: {exc}") from exc


@router.post("/rotate", response_model=BackupRotationResponse)
async def rotate_backups(
    _current_user: Annotated[User, Depends(get_current_user)],
) -> BackupRotationResponse:
    """Remove backups older than retention period (30 days).

    Returns counts of deleted backups per type.
    """
    try:
        counts = await backup_service.rotate_backups()
        return BackupRotationResponse(
            postgres_deleted=counts["postgres"],
            redis_deleted=counts["redis"],
            retention_days=30,
        )
    except Exception as exc:
        await logger.aexception("backup_rotation_error")
        raise HTTPException(status_code=500, detail=f"Backup rotasyonu basarisiz: {exc}") from exc


@router.post("/verify", response_model=BackupVerifyResponse)
async def verify_backup(
    request: BackupVerifyRequest,
    _current_user: Annotated[User, Depends(get_current_user)],
) -> BackupVerifyResponse:
    """Verify a backup's integrity.

    Downloads the backup from S3, checks gzip integrity, and for PostgreSQL
    backups, runs pg_restore --list to verify the dump header.
    """
    try:
        result = await backup_service.verify_backup(s3_key=request.s3_key)
        return BackupVerifyResponse(**result)
    except BackupError as exc:
        await logger.aexception("backup_verify_failed", s3_key=request.s3_key)
        raise HTTPException(
            status_code=500,
            detail=f"Backup dogrulama basarisiz: {exc}",
        ) from exc
