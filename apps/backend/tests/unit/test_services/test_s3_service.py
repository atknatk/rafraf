"""Unit tests for S3Service."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.s3_service import S3Service, S3ServiceError


class TestBuildKey:
    """Tests for S3Service._build_key."""

    def test_basic_key(self) -> None:
        """_build_key should construct key from project_id and path."""
        service = S3Service()
        key = service._build_key("proj-1", "docs/report.pdf")
        assert key == "projects/proj-1/docs/report.pdf"

    def test_strips_leading_slash(self) -> None:
        """_build_key should strip leading slash from path."""
        service = S3Service()
        key = service._build_key("proj-1", "/docs/report.pdf")
        assert key == "projects/proj-1/docs/report.pdf"

    def test_multiple_leading_slashes(self) -> None:
        """_build_key should strip multiple leading slashes."""
        service = S3Service()
        key = service._build_key("proj-1", "///docs/report.pdf")
        assert key == "projects/proj-1/docs/report.pdf"

    def test_empty_path(self) -> None:
        """_build_key should handle empty path."""
        service = S3Service()
        key = service._build_key("proj-1", "")
        assert key == "projects/proj-1/"

    def test_nested_path(self) -> None:
        """_build_key should handle deeply nested paths."""
        service = S3Service()
        key = service._build_key("proj-1", "a/b/c/d/file.txt")
        assert key == "projects/proj-1/a/b/c/d/file.txt"


class TestUploadFile:
    """Tests for S3Service.upload_file."""

    async def test_upload_success(self) -> None:
        """upload_file should call S3 put_object and return metadata."""
        service = S3Service()
        content = b"Hello, S3!"

        mock_s3 = AsyncMock()
        mock_s3.put_object = AsyncMock(return_value={})
        mock_s3.__aenter__ = AsyncMock(return_value=mock_s3)
        mock_s3.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.client = MagicMock(return_value=mock_s3)

        with patch.object(service, "_get_session", return_value=mock_session):
            result = await service.upload_file("proj-1", "test.txt", content)

        assert result["key"] == "projects/proj-1/test.txt"
        assert result["size"] == str(len(content))
        assert result["content_type"] == "application/octet-stream"
        mock_s3.put_object.assert_called_once()

    async def test_upload_custom_content_type(self) -> None:
        """upload_file should pass content_type to put_object."""
        service = S3Service()
        content = b"<html></html>"

        mock_s3 = AsyncMock()
        mock_s3.put_object = AsyncMock(return_value={})
        mock_s3.__aenter__ = AsyncMock(return_value=mock_s3)
        mock_s3.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.client = MagicMock(return_value=mock_s3)

        with patch.object(service, "_get_session", return_value=mock_session):
            result = await service.upload_file(
                "proj-1", "index.html", content, content_type="text/html"
            )

        assert result["content_type"] == "text/html"

    async def test_upload_exceeds_size_limit(self) -> None:
        """upload_file should raise S3ServiceError for oversized files."""
        service = S3Service()
        # Create content larger than 100MB limit
        content = b"x" * (100 * 1024 * 1024 + 1)

        with pytest.raises(S3ServiceError, match="Dosya boyutu limiti"):
            await service.upload_file("proj-1", "large.bin", content)

    async def test_upload_at_exact_limit(self) -> None:
        """upload_file should succeed for files exactly at the limit."""
        service = S3Service()
        content = b"x" * (100 * 1024 * 1024)

        mock_s3 = AsyncMock()
        mock_s3.put_object = AsyncMock(return_value={})
        mock_s3.__aenter__ = AsyncMock(return_value=mock_s3)
        mock_s3.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.client = MagicMock(return_value=mock_s3)

        with patch.object(service, "_get_session", return_value=mock_session):
            result = await service.upload_file("proj-1", "exact.bin", content)

        assert result["key"] == "projects/proj-1/exact.bin"

    async def test_upload_s3_error(self) -> None:
        """upload_file should wrap boto errors in S3ServiceError."""
        from botocore.exceptions import ClientError

        service = S3Service()
        content = b"test"

        mock_s3 = AsyncMock()
        mock_s3.put_object = AsyncMock(
            side_effect=ClientError(
                {"Error": {"Code": "AccessDenied", "Message": "Forbidden"}},
                "PutObject",
            )
        )
        mock_s3.__aenter__ = AsyncMock(return_value=mock_s3)
        mock_s3.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.client = MagicMock(return_value=mock_s3)

        with (
            patch.object(service, "_get_session", return_value=mock_session),
            pytest.raises(S3ServiceError, match="S3 yukleme hatasi"),
        ):
            await service.upload_file("proj-1", "test.txt", content)


class TestDownloadFile:
    """Tests for S3Service.download_file."""

    async def test_download_success(self) -> None:
        """download_file should return file content as bytes."""
        service = S3Service()
        expected_content = b"file contents here"

        mock_body = AsyncMock()
        mock_body.read = AsyncMock(return_value=expected_content)

        mock_s3 = AsyncMock()
        mock_s3.get_object = AsyncMock(return_value={"Body": mock_body})
        mock_s3.__aenter__ = AsyncMock(return_value=mock_s3)
        mock_s3.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.client = MagicMock(return_value=mock_s3)

        with patch.object(service, "_get_session", return_value=mock_session):
            result = await service.download_file("proj-1", "test.txt")

        assert result == expected_content
        mock_s3.get_object.assert_called_once_with(
            Bucket=service._bucket, Key="projects/proj-1/test.txt"
        )

    async def test_download_s3_error(self) -> None:
        """download_file should wrap boto errors in S3ServiceError."""
        from botocore.exceptions import ClientError

        service = S3Service()

        mock_s3 = AsyncMock()
        mock_s3.get_object = AsyncMock(
            side_effect=ClientError(
                {"Error": {"Code": "NoSuchKey", "Message": "Not Found"}},
                "GetObject",
            )
        )
        mock_s3.__aenter__ = AsyncMock(return_value=mock_s3)
        mock_s3.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.client = MagicMock(return_value=mock_s3)

        with (
            patch.object(service, "_get_session", return_value=mock_session),
            pytest.raises(S3ServiceError, match="S3 indirme hatasi"),
        ):
            await service.download_file("proj-1", "nonexistent.txt")


class TestListFiles:
    """Tests for S3Service.list_files."""

    async def test_list_files_success(self) -> None:
        """list_files should return file metadata list."""
        from datetime import datetime

        service = S3Service()

        mock_s3 = AsyncMock()
        mock_s3.list_objects_v2 = AsyncMock(
            return_value={
                "Contents": [
                    {
                        "Key": "projects/proj-1/file1.txt",
                        "Size": 1024,
                        "LastModified": datetime(2026, 1, 1, 12, 0, 0),
                    },
                    {
                        "Key": "projects/proj-1/file2.pdf",
                        "Size": 2048,
                        "LastModified": datetime(2026, 1, 2, 12, 0, 0),
                    },
                ]
            }
        )
        mock_s3.__aenter__ = AsyncMock(return_value=mock_s3)
        mock_s3.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.client = MagicMock(return_value=mock_s3)

        with patch.object(service, "_get_session", return_value=mock_session):
            files = await service.list_files("proj-1")

        assert len(files) == 2
        assert files[0]["key"] == "projects/proj-1/file1.txt"
        assert files[0]["size"] == "1024"
        assert files[1]["key"] == "projects/proj-1/file2.pdf"

    async def test_list_files_empty(self) -> None:
        """list_files should return empty list when no files found."""
        service = S3Service()

        mock_s3 = AsyncMock()
        mock_s3.list_objects_v2 = AsyncMock(return_value={})
        mock_s3.__aenter__ = AsyncMock(return_value=mock_s3)
        mock_s3.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.client = MagicMock(return_value=mock_s3)

        with patch.object(service, "_get_session", return_value=mock_session):
            files = await service.list_files("proj-1")

        assert files == []

    async def test_list_files_with_prefix(self) -> None:
        """list_files should pass prefix to S3."""
        service = S3Service()

        mock_s3 = AsyncMock()
        mock_s3.list_objects_v2 = AsyncMock(return_value={"Contents": []})
        mock_s3.__aenter__ = AsyncMock(return_value=mock_s3)
        mock_s3.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.client = MagicMock(return_value=mock_s3)

        with patch.object(service, "_get_session", return_value=mock_session):
            await service.list_files("proj-1", prefix="docs/")

        mock_s3.list_objects_v2.assert_called_once_with(
            Bucket=service._bucket,
            Prefix="projects/proj-1/docs/",
            MaxKeys=100,
        )

    async def test_list_files_custom_max_keys(self) -> None:
        """list_files should respect max_keys parameter."""
        service = S3Service()

        mock_s3 = AsyncMock()
        mock_s3.list_objects_v2 = AsyncMock(return_value={"Contents": []})
        mock_s3.__aenter__ = AsyncMock(return_value=mock_s3)
        mock_s3.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.client = MagicMock(return_value=mock_s3)

        with patch.object(service, "_get_session", return_value=mock_session):
            await service.list_files("proj-1", max_keys=10)

        call_kwargs = mock_s3.list_objects_v2.call_args
        assert call_kwargs.kwargs["MaxKeys"] == 10

    async def test_list_files_s3_error(self) -> None:
        """list_files should wrap boto errors in S3ServiceError."""
        from botocore.exceptions import ClientError

        service = S3Service()

        mock_s3 = AsyncMock()
        mock_s3.list_objects_v2 = AsyncMock(
            side_effect=ClientError(
                {"Error": {"Code": "NoSuchBucket", "Message": "Not Found"}},
                "ListObjectsV2",
            )
        )
        mock_s3.__aenter__ = AsyncMock(return_value=mock_s3)
        mock_s3.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.client = MagicMock(return_value=mock_s3)

        with (
            patch.object(service, "_get_session", return_value=mock_session),
            pytest.raises(S3ServiceError, match="S3 listeleme hatasi"),
        ):
            await service.list_files("proj-1")


class TestDeleteFile:
    """Tests for S3Service.delete_file."""

    async def test_delete_success(self) -> None:
        """delete_file should call delete_object and return status."""
        service = S3Service()

        mock_s3 = AsyncMock()
        mock_s3.delete_object = AsyncMock(return_value={})
        mock_s3.__aenter__ = AsyncMock(return_value=mock_s3)
        mock_s3.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.client = MagicMock(return_value=mock_s3)

        with patch.object(service, "_get_session", return_value=mock_session):
            result = await service.delete_file("proj-1", "test.txt")

        assert result["status"] == "deleted"
        assert result["key"] == "projects/proj-1/test.txt"
        mock_s3.delete_object.assert_called_once_with(
            Bucket=service._bucket, Key="projects/proj-1/test.txt"
        )

    async def test_delete_s3_error(self) -> None:
        """delete_file should wrap boto errors in S3ServiceError."""
        from botocore.exceptions import ClientError

        service = S3Service()

        mock_s3 = AsyncMock()
        mock_s3.delete_object = AsyncMock(
            side_effect=ClientError(
                {"Error": {"Code": "AccessDenied", "Message": "Forbidden"}},
                "DeleteObject",
            )
        )
        mock_s3.__aenter__ = AsyncMock(return_value=mock_s3)
        mock_s3.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.client = MagicMock(return_value=mock_s3)

        with (
            patch.object(service, "_get_session", return_value=mock_session),
            pytest.raises(S3ServiceError, match="S3 silme hatasi"),
        ):
            await service.delete_file("proj-1", "test.txt")


class TestGeneratePresignedUploadUrl:
    """Tests for S3Service.generate_presigned_upload_url."""

    async def test_presigned_upload_url_success(self) -> None:
        """generate_presigned_upload_url should return URL dict."""
        service = S3Service()

        mock_s3 = AsyncMock()
        mock_s3.generate_presigned_url = AsyncMock(
            return_value="https://s3.example.com/presigned-upload"
        )
        mock_s3.__aenter__ = AsyncMock(return_value=mock_s3)
        mock_s3.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.client = MagicMock(return_value=mock_s3)

        with patch.object(service, "_get_session", return_value=mock_session):
            result = await service.generate_presigned_upload_url("proj-1", "upload.pdf")

        assert result["url"] == "https://s3.example.com/presigned-upload"
        assert result["key"] == "projects/proj-1/upload.pdf"
        assert result["method"] == "PUT"
        assert result["expiration_seconds"] == "3600"

    async def test_presigned_upload_url_custom_expiration(self) -> None:
        """generate_presigned_upload_url should accept custom expiration."""
        service = S3Service()

        mock_s3 = AsyncMock()
        mock_s3.generate_presigned_url = AsyncMock(return_value="https://s3.example.com/presigned")
        mock_s3.__aenter__ = AsyncMock(return_value=mock_s3)
        mock_s3.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.client = MagicMock(return_value=mock_s3)

        with patch.object(service, "_get_session", return_value=mock_session):
            result = await service.generate_presigned_upload_url(
                "proj-1", "upload.pdf", expiration=7200
            )

        assert result["expiration_seconds"] == "7200"
        mock_s3.generate_presigned_url.assert_called_once_with(
            "put_object",
            Params={
                "Bucket": service._bucket,
                "Key": "projects/proj-1/upload.pdf",
                "ContentType": "application/octet-stream",
            },
            ExpiresIn=7200,
        )

    async def test_presigned_upload_url_s3_error(self) -> None:
        """generate_presigned_upload_url should wrap errors."""
        from botocore.exceptions import ClientError

        service = S3Service()

        mock_s3 = AsyncMock()
        mock_s3.generate_presigned_url = AsyncMock(
            side_effect=ClientError(
                {"Error": {"Code": "AccessDenied", "Message": "Forbidden"}},
                "GeneratePresignedUrl",
            )
        )
        mock_s3.__aenter__ = AsyncMock(return_value=mock_s3)
        mock_s3.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.client = MagicMock(return_value=mock_s3)

        with (
            patch.object(service, "_get_session", return_value=mock_session),
            pytest.raises(S3ServiceError, match="S3 pre-signed URL"),
        ):
            await service.generate_presigned_upload_url("proj-1", "upload.pdf")


class TestGeneratePresignedDownloadUrl:
    """Tests for S3Service.generate_presigned_download_url."""

    async def test_presigned_download_url_success(self) -> None:
        """generate_presigned_download_url should return URL dict."""
        service = S3Service()

        mock_s3 = AsyncMock()
        mock_s3.generate_presigned_url = AsyncMock(
            return_value="https://s3.example.com/presigned-download"
        )
        mock_s3.__aenter__ = AsyncMock(return_value=mock_s3)
        mock_s3.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.client = MagicMock(return_value=mock_s3)

        with patch.object(service, "_get_session", return_value=mock_session):
            result = await service.generate_presigned_download_url("proj-1", "download.pdf")

        assert result["url"] == "https://s3.example.com/presigned-download"
        assert result["key"] == "projects/proj-1/download.pdf"
        assert result["method"] == "GET"
        assert result["expiration_seconds"] == "3600"

    async def test_presigned_download_url_custom_expiration(self) -> None:
        """generate_presigned_download_url should accept custom expiration."""
        service = S3Service()

        mock_s3 = AsyncMock()
        mock_s3.generate_presigned_url = AsyncMock(return_value="https://s3.example.com/presigned")
        mock_s3.__aenter__ = AsyncMock(return_value=mock_s3)
        mock_s3.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.client = MagicMock(return_value=mock_s3)

        with patch.object(service, "_get_session", return_value=mock_session):
            result = await service.generate_presigned_download_url(
                "proj-1", "download.pdf", expiration=1800
            )

        assert result["expiration_seconds"] == "1800"

    async def test_presigned_download_url_s3_error(self) -> None:
        """generate_presigned_download_url should wrap errors."""
        from botocore.exceptions import ClientError

        service = S3Service()

        mock_s3 = AsyncMock()
        mock_s3.generate_presigned_url = AsyncMock(
            side_effect=ClientError(
                {"Error": {"Code": "AccessDenied", "Message": "Forbidden"}},
                "GeneratePresignedUrl",
            )
        )
        mock_s3.__aenter__ = AsyncMock(return_value=mock_s3)
        mock_s3.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.client = MagicMock(return_value=mock_s3)

        with (
            patch.object(service, "_get_session", return_value=mock_session),
            pytest.raises(S3ServiceError, match="S3 pre-signed URL"),
        ):
            await service.generate_presigned_download_url("proj-1", "download.pdf")


class TestFormatResult:
    """Tests for S3Service.format_result."""

    def test_format_dict(self) -> None:
        """format_result should serialize dict to JSON."""
        result = S3Service.format_result({"key": "value"})
        assert '"key": "value"' in result

    def test_format_list(self) -> None:
        """format_result should serialize list to JSON."""
        result = S3Service.format_result([{"a": 1}, {"b": 2}])
        assert '"a": 1' in result
        assert '"b": 2' in result

    def test_format_empty_list(self) -> None:
        """format_result should serialize empty list."""
        result = S3Service.format_result([])
        assert result == "[]"


class TestS3ServiceError:
    """Tests for S3ServiceError exception."""

    def test_error_message(self) -> None:
        """S3ServiceError should store message."""
        error = S3ServiceError("Test error", operation="upload")
        assert str(error) == "Test error"
        assert error.operation == "upload"

    def test_error_default_operation(self) -> None:
        """S3ServiceError should have empty operation by default."""
        error = S3ServiceError("Test error")
        assert error.operation == ""
