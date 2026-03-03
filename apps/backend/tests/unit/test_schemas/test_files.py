"""Unit tests for file sharing Pydantic schemas."""

import pytest
from pydantic import ValidationError

from app.schemas.files import (
    FileDownloadURLRequest,
    FileDownloadURLResponse,
    FileUploadURLRequest,
    FileUploadURLResponse,
)


class TestFileUploadURLRequest:
    """Tests for FileUploadURLRequest schema."""

    def test_create_valid_request(self) -> None:
        request = FileUploadURLRequest(
            project_id="123e4567-e89b-12d3-a456-426614174000",
            file_name="rapor.pdf",
            content_type="application/pdf",
            file_size=1_000_000,
        )
        assert request.file_name == "rapor.pdf"
        assert request.content_type == "application/pdf"
        assert request.file_size == 1_000_000

    def test_rejects_empty_file_name(self) -> None:
        with pytest.raises(ValidationError):
            FileUploadURLRequest(
                project_id="123",
                file_name="",
                content_type="application/pdf",
                file_size=1000,
            )

    def test_rejects_zero_file_size(self) -> None:
        with pytest.raises(ValidationError):
            FileUploadURLRequest(
                project_id="123",
                file_name="test.pdf",
                content_type="application/pdf",
                file_size=0,
            )

    def test_rejects_negative_file_size(self) -> None:
        with pytest.raises(ValidationError):
            FileUploadURLRequest(
                project_id="123",
                file_name="test.pdf",
                content_type="application/pdf",
                file_size=-100,
            )

    def test_rejects_file_size_over_50mb(self) -> None:
        with pytest.raises(ValidationError):
            FileUploadURLRequest(
                project_id="123",
                file_name="huge.zip",
                content_type="application/zip",
                file_size=52_428_801,  # 50MB + 1 byte
            )

    def test_accepts_file_size_exactly_50mb(self) -> None:
        request = FileUploadURLRequest(
            project_id="123",
            file_name="exact.zip",
            content_type="application/zip",
            file_size=52_428_800,  # Exactly 50MB
        )
        assert request.file_size == 52_428_800

    def test_rejects_file_name_over_255_chars(self) -> None:
        with pytest.raises(ValidationError):
            FileUploadURLRequest(
                project_id="123",
                file_name="a" * 256,
                content_type="application/pdf",
                file_size=1000,
            )

    def test_requires_all_fields(self) -> None:
        with pytest.raises(ValidationError):
            FileUploadURLRequest(
                project_id="123",
                file_name="test.pdf",
            )  # type: ignore[call-arg]


class TestFileUploadURLResponse:
    """Tests for FileUploadURLResponse frozen model."""

    def test_create_valid_response(self) -> None:
        response = FileUploadURLResponse(
            upload_url="https://s3.amazonaws.com/bucket/key?X-Amz-Signature=abc",
            file_key="projects/123/rapor.pdf",
            expiration_seconds=3600,
        )
        assert response.upload_url.startswith("https://")
        assert response.file_key == "projects/123/rapor.pdf"
        assert response.expiration_seconds == 3600

    def test_response_is_frozen(self) -> None:
        response = FileUploadURLResponse(
            upload_url="https://example.com",
            file_key="key",
            expiration_seconds=3600,
        )
        with pytest.raises(ValidationError):
            response.upload_url = "changed"  # type: ignore[misc]


class TestFileDownloadURLRequest:
    """Tests for FileDownloadURLRequest schema."""

    def test_create_valid_request(self) -> None:
        request = FileDownloadURLRequest(
            project_id="123",
            file_key="projects/123/rapor.pdf",
        )
        assert request.project_id == "123"
        assert request.file_key == "projects/123/rapor.pdf"

    def test_rejects_empty_file_key(self) -> None:
        with pytest.raises(ValidationError):
            FileDownloadURLRequest(
                project_id="123",
                file_key="",
            )

    def test_requires_all_fields(self) -> None:
        with pytest.raises(ValidationError):
            FileDownloadURLRequest(
                project_id="123",
            )  # type: ignore[call-arg]


class TestFileDownloadURLResponse:
    """Tests for FileDownloadURLResponse frozen model."""

    def test_create_valid_response(self) -> None:
        response = FileDownloadURLResponse(
            download_url="https://s3.amazonaws.com/bucket/key?X-Amz-Signature=abc",
            file_key="projects/123/rapor.pdf",
            expiration_seconds=3600,
        )
        assert response.download_url.startswith("https://")
        assert response.file_key == "projects/123/rapor.pdf"

    def test_response_is_frozen(self) -> None:
        response = FileDownloadURLResponse(
            download_url="https://example.com",
            file_key="key",
            expiration_seconds=3600,
        )
        with pytest.raises(ValidationError):
            response.download_url = "changed"  # type: ignore[misc]
