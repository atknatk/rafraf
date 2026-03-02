"""S3 file management service - async client for AWS S3 via aioboto3."""

import json
from datetime import datetime

import aioboto3
import structlog
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import get_settings

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

# Default pre-signed URL expiration (1 hour)
_PRESIGNED_URL_EXPIRATION = 3600

# Maximum allowed file size for upload (100 MB)
_MAX_FILE_SIZE_BYTES = 100 * 1024 * 1024


class S3ServiceError(Exception):
    """Raised when an S3 operation fails."""

    def __init__(self, message: str, operation: str = "") -> None:
        self.operation = operation
        super().__init__(message)


class S3Service:
    """Async S3 client using aioboto3.

    Provides file upload, download, listing, deletion, and pre-signed URL
    generation for the RafRaf project bucket.

    Bucket structure: rafraf-{env}/projects/{project_id}/...
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._bucket = settings.aws_s3_bucket
        self._access_key = settings.aws_access_key_id
        self._secret_key = settings.aws_secret_access_key
        self._region = settings.aws_region
        self._session: aioboto3.Session | None = None

    def _get_session(self) -> aioboto3.Session:
        """Get or create the aioboto3 session.

        Returns:
            Configured aioboto3.Session instance.
        """
        if self._session is None:
            self._session = aioboto3.Session(
                aws_access_key_id=self._access_key,
                aws_secret_access_key=self._secret_key,
                region_name=self._region,
            )
        return self._session

    def _build_key(self, project_id: str, path: str) -> str:
        """Build an S3 object key from project ID and path.

        Args:
            project_id: Project identifier.
            path: Relative file path within the project.

        Returns:
            Full S3 object key.
        """
        # Remove leading slashes from path
        clean_path = path.lstrip("/")
        return f"projects/{project_id}/{clean_path}"

    async def upload_file(
        self,
        project_id: str,
        path: str,
        content: bytes,
        content_type: str = "application/octet-stream",
    ) -> dict[str, str]:
        """Upload a file to S3.

        Args:
            project_id: Project identifier.
            path: Relative file path within the project.
            content: File content as bytes.
            content_type: MIME type of the file.

        Returns:
            Dict with key, bucket, and size info.

        Raises:
            S3ServiceError: On upload failure or size limit exceeded.
        """
        if len(content) > _MAX_FILE_SIZE_BYTES:
            raise S3ServiceError(
                f"Dosya boyutu limiti asildi: {len(content)} bytes > {_MAX_FILE_SIZE_BYTES} bytes",
                operation="upload_file",
            )

        key = self._build_key(project_id, path)
        session = self._get_session()

        try:
            async with session.client("s3") as s3:
                await s3.put_object(
                    Bucket=self._bucket,
                    Key=key,
                    Body=content,
                    ContentType=content_type,
                )

            await logger.ainfo(
                "s3_file_uploaded",
                bucket=self._bucket,
                key=key,
                size=len(content),
                content_type=content_type,
            )

            return {
                "bucket": self._bucket,
                "key": key,
                "size": str(len(content)),
                "content_type": content_type,
            }
        except (BotoCoreError, ClientError) as exc:
            await logger.aexception(
                "s3_upload_error",
                bucket=self._bucket,
                key=key,
            )
            raise S3ServiceError(
                f"S3 yukleme hatasi: {exc}",
                operation="upload_file",
            ) from exc

    async def download_file(self, project_id: str, path: str) -> bytes:
        """Download a file from S3.

        Args:
            project_id: Project identifier.
            path: Relative file path within the project.

        Returns:
            File content as bytes.

        Raises:
            S3ServiceError: On download failure.
        """
        key = self._build_key(project_id, path)
        session = self._get_session()

        try:
            async with session.client("s3") as s3:
                response = await s3.get_object(
                    Bucket=self._bucket,
                    Key=key,
                )
                body = await response["Body"].read()

            await logger.ainfo(
                "s3_file_downloaded",
                bucket=self._bucket,
                key=key,
                size=len(body),
            )

            result: bytes = body
            return result
        except (BotoCoreError, ClientError) as exc:
            await logger.aexception(
                "s3_download_error",
                bucket=self._bucket,
                key=key,
            )
            raise S3ServiceError(
                f"S3 indirme hatasi: {exc}",
                operation="download_file",
            ) from exc

    async def list_files(
        self,
        project_id: str,
        prefix: str = "",
        max_keys: int = 100,
    ) -> list[dict[str, str]]:
        """List files in a project's S3 prefix.

        Args:
            project_id: Project identifier.
            prefix: Additional prefix filter within the project directory.
            max_keys: Maximum number of keys to return.

        Returns:
            List of dicts with key, size, and last_modified info.

        Raises:
            S3ServiceError: On listing failure.
        """
        base_prefix = self._build_key(project_id, prefix)
        session = self._get_session()

        try:
            async with session.client("s3") as s3:
                response = await s3.list_objects_v2(
                    Bucket=self._bucket,
                    Prefix=base_prefix,
                    MaxKeys=max_keys,
                )

            contents = response.get("Contents", [])
            files: list[dict[str, str]] = []
            for obj in contents:
                last_modified = obj.get("LastModified")
                last_modified_str = ""
                if isinstance(last_modified, datetime):
                    last_modified_str = last_modified.isoformat()
                elif last_modified is not None:
                    last_modified_str = str(last_modified)

                files.append(
                    {
                        "key": str(obj.get("Key", "")),
                        "size": str(obj.get("Size", 0)),
                        "last_modified": last_modified_str,
                    }
                )

            await logger.ainfo(
                "s3_files_listed",
                bucket=self._bucket,
                prefix=base_prefix,
                count=len(files),
            )

            return files
        except (BotoCoreError, ClientError) as exc:
            await logger.aexception(
                "s3_list_error",
                bucket=self._bucket,
                prefix=base_prefix,
            )
            raise S3ServiceError(
                f"S3 listeleme hatasi: {exc}",
                operation="list_files",
            ) from exc

    async def delete_file(self, project_id: str, path: str) -> dict[str, str]:
        """Delete a file from S3.

        Args:
            project_id: Project identifier.
            path: Relative file path within the project.

        Returns:
            Dict with deleted key info.

        Raises:
            S3ServiceError: On deletion failure.
        """
        key = self._build_key(project_id, path)
        session = self._get_session()

        try:
            async with session.client("s3") as s3:
                await s3.delete_object(
                    Bucket=self._bucket,
                    Key=key,
                )

            await logger.ainfo(
                "s3_file_deleted",
                bucket=self._bucket,
                key=key,
            )

            return {"status": "deleted", "key": key}
        except (BotoCoreError, ClientError) as exc:
            await logger.aexception(
                "s3_delete_error",
                bucket=self._bucket,
                key=key,
            )
            raise S3ServiceError(
                f"S3 silme hatasi: {exc}",
                operation="delete_file",
            ) from exc

    async def generate_presigned_upload_url(
        self,
        project_id: str,
        path: str,
        content_type: str = "application/octet-stream",
        expiration: int = _PRESIGNED_URL_EXPIRATION,
    ) -> dict[str, str]:
        """Generate a pre-signed URL for file upload.

        Args:
            project_id: Project identifier.
            path: Relative file path within the project.
            content_type: Expected MIME type.
            expiration: URL validity in seconds (default: 1 hour).

        Returns:
            Dict with url, key, and expiration info.

        Raises:
            S3ServiceError: On URL generation failure.
        """
        key = self._build_key(project_id, path)
        session = self._get_session()

        try:
            async with session.client("s3") as s3:
                url: str = await s3.generate_presigned_url(
                    "put_object",
                    Params={
                        "Bucket": self._bucket,
                        "Key": key,
                        "ContentType": content_type,
                    },
                    ExpiresIn=expiration,
                )

            await logger.ainfo(
                "s3_presigned_upload_url_generated",
                bucket=self._bucket,
                key=key,
                expiration=expiration,
            )

            return {
                "url": url,
                "key": key,
                "method": "PUT",
                "content_type": content_type,
                "expiration_seconds": str(expiration),
            }
        except (BotoCoreError, ClientError) as exc:
            await logger.aexception(
                "s3_presigned_url_error",
                bucket=self._bucket,
                key=key,
            )
            raise S3ServiceError(
                f"S3 pre-signed URL olusturma hatasi: {exc}",
                operation="generate_presigned_upload_url",
            ) from exc

    async def generate_presigned_download_url(
        self,
        project_id: str,
        path: str,
        expiration: int = _PRESIGNED_URL_EXPIRATION,
    ) -> dict[str, str]:
        """Generate a pre-signed URL for file download.

        Args:
            project_id: Project identifier.
            path: Relative file path within the project.
            expiration: URL validity in seconds (default: 1 hour).

        Returns:
            Dict with url, key, and expiration info.

        Raises:
            S3ServiceError: On URL generation failure.
        """
        key = self._build_key(project_id, path)
        session = self._get_session()

        try:
            async with session.client("s3") as s3:
                url: str = await s3.generate_presigned_url(
                    "get_object",
                    Params={
                        "Bucket": self._bucket,
                        "Key": key,
                    },
                    ExpiresIn=expiration,
                )

            await logger.ainfo(
                "s3_presigned_download_url_generated",
                bucket=self._bucket,
                key=key,
                expiration=expiration,
            )

            return {
                "url": url,
                "key": key,
                "method": "GET",
                "expiration_seconds": str(expiration),
            }
        except (BotoCoreError, ClientError) as exc:
            await logger.aexception(
                "s3_presigned_download_url_error",
                bucket=self._bucket,
                key=key,
            )
            raise S3ServiceError(
                f"S3 pre-signed URL olusturma hatasi: {exc}",
                operation="generate_presigned_download_url",
            ) from exc

    @staticmethod
    def format_result(data: object) -> str:
        """Format result data as JSON string for Claude.

        Args:
            data: Data to serialize (dict, list, or Pydantic model).

        Returns:
            JSON string.
        """
        if isinstance(data, list):
            items = [item.model_dump() if hasattr(item, "model_dump") else item for item in data]
            return json.dumps(items, ensure_ascii=False, indent=2)
        if hasattr(data, "model_dump"):
            return json.dumps(
                data.model_dump(),
                ensure_ascii=False,
                indent=2,
            )
        return json.dumps(data, ensure_ascii=False, indent=2)
