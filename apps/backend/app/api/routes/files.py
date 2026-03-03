"""REST endpoints for file sharing - pre-signed URL generation."""

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.files import (
    FileDownloadURLRequest,
    FileDownloadURLResponse,
    FileUploadURLRequest,
    FileUploadURLResponse,
)
from app.services.s3_service import S3Service

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/files", tags=["files"])

# Pre-signed URL expiration: 1 hour
_PRESIGNED_URL_EXPIRATION = 3600

# Allowed MIME types for upload
_ALLOWED_CONTENT_TYPES: frozenset[str] = frozenset(
    {
        # Images
        "image/png",
        "image/jpeg",
        "image/gif",
        # Documents
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        # Text
        "text/plain",
        "text/markdown",
        # Code
        "text/x-python",
        "text/javascript",
        "text/typescript",
        "text/x-swift",
        "application/x-python-code",
        "application/javascript",
        # Log
        "text/x-log",
        # Archive
        "application/zip",
        # Fallback for unknown text types
        "application/octet-stream",
    }
)


@router.post("/upload-url", response_model=FileUploadURLResponse)
async def create_upload_url(
    body: FileUploadURLRequest,
    current_user: Annotated[User, Depends(get_current_user)],
) -> FileUploadURLResponse:
    """Generate a pre-signed S3 upload URL for file sharing.

    The iOS client uses this URL to upload files directly to S3 via PUT request.
    """
    await logger.ainfo(
        "file_upload_url_requested",
        project_id=body.project_id,
        file_name=body.file_name,
        content_type=body.content_type,
        file_size=body.file_size,
        user_id=str(current_user.id),
    )

    s3_service = S3Service()
    result = await s3_service.generate_presigned_upload_url(
        project_id=body.project_id,
        path=body.file_name,
        content_type=body.content_type,
        expiration=_PRESIGNED_URL_EXPIRATION,
    )

    return FileUploadURLResponse(
        upload_url=result["url"],
        file_key=result["key"],
        expiration_seconds=_PRESIGNED_URL_EXPIRATION,
    )


@router.post("/download-url", response_model=FileDownloadURLResponse)
async def create_download_url(
    body: FileDownloadURLRequest,
    current_user: Annotated[User, Depends(get_current_user)],
) -> FileDownloadURLResponse:
    """Generate a pre-signed S3 download URL for file sharing.

    The iOS client uses this URL to download files directly from S3 via GET request.
    """
    await logger.ainfo(
        "file_download_url_requested",
        project_id=body.project_id,
        file_key=body.file_key,
        user_id=str(current_user.id),
    )

    s3_service = S3Service()

    # Extract the relative path from the file_key
    # file_key format: projects/{project_id}/{path}
    prefix = f"projects/{body.project_id}/"
    if body.file_key.startswith(prefix):
        relative_path = body.file_key[len(prefix) :]
    else:
        relative_path = body.file_key

    result = await s3_service.generate_presigned_download_url(
        project_id=body.project_id,
        path=relative_path,
        expiration=_PRESIGNED_URL_EXPIRATION,
    )

    return FileDownloadURLResponse(
        download_url=result["url"],
        file_key=result["key"],
        expiration_seconds=_PRESIGNED_URL_EXPIRATION,
    )
