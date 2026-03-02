"""Unit tests for S3Uploader."""

from __future__ import annotations

import base64
from unittest.mock import MagicMock, patch

import pytest

from agent.upload.s3_uploader import (
    S3UploadError,
    S3Uploader,
    bytes_to_base64,
)


# --- Fixtures ---


@pytest.fixture
def mock_s3_client() -> MagicMock:
    """Mock boto3 S3 client olusturur."""
    client = MagicMock()
    client.put_object = MagicMock(return_value={"ResponseMetadata": {"HTTPStatusCode": 200}})
    return client


@pytest.fixture
def s3_uploader(mock_s3_client: MagicMock) -> S3Uploader:
    """Test icin S3Uploader instance olusturur."""
    return S3Uploader(
        bucket="test-bucket",
        region="eu-west-1",
        client=mock_s3_client,
    )


# --- S3Uploader Init Tests ---


class TestS3UploaderInit:
    """S3Uploader __init__ testleri."""

    def test_create_with_defaults(self) -> None:
        """Varsayilan parametreler ile olusturulur."""
        uploader = S3Uploader(bucket="my-bucket")
        assert uploader._bucket == "my-bucket"
        assert uploader._region == "eu-west-1"
        assert uploader._client is None

    def test_create_with_custom_region(self) -> None:
        """Ozel region ile olusturulur."""
        uploader = S3Uploader(bucket="my-bucket", region="us-east-1")
        assert uploader._region == "us-east-1"

    def test_create_with_injected_client(self, mock_s3_client: MagicMock) -> None:
        """Enjekte edilen client kullanilir."""
        uploader = S3Uploader(bucket="my-bucket", client=mock_s3_client)
        assert uploader._client is mock_s3_client


# --- _get_client Tests ---


class TestGetClient:
    """S3Uploader._get_client testleri."""

    def test_returns_injected_client(
        self,
        s3_uploader: S3Uploader,
        mock_s3_client: MagicMock,
    ) -> None:
        """Enjekte edilen client dondurulur."""
        client = s3_uploader._get_client()
        assert client is mock_s3_client

    def test_creates_client_if_not_injected(self) -> None:
        """Client enjekte edilmemisse boto3 ile olusturur."""
        mock_boto3 = MagicMock()
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        uploader = S3Uploader(bucket="test-bucket")

        with patch.dict("sys.modules", {"boto3": mock_boto3}):
            client = uploader._get_client()
            assert client is mock_client
            mock_boto3.client.assert_called_once_with("s3", region_name="eu-west-1")

    def test_raises_error_if_boto3_not_installed(self) -> None:
        """boto3 yuklu degilse S3UploadError firlatir."""
        uploader = S3Uploader(bucket="test-bucket")

        with patch.dict("sys.modules", {"boto3": None}):
            with pytest.raises(S3UploadError, match="boto3 yuklu degil"):
                uploader._get_client()

    def test_raises_error_on_client_creation_failure(self) -> None:
        """Client olusturma basarisiz olursa S3UploadError firlatir."""
        mock_boto3 = MagicMock()
        mock_boto3.client.side_effect = Exception("AWS credentials not found")

        uploader = S3Uploader(bucket="test-bucket")

        with patch.dict("sys.modules", {"boto3": mock_boto3}):
            with pytest.raises(S3UploadError, match="S3 client olusturulamadi"):
                uploader._get_client()


# --- _upload_bytes_sync Tests ---


class TestUploadBytesSync:
    """S3Uploader._upload_bytes_sync testleri."""

    def test_successful_upload_returns_url(
        self,
        s3_uploader: S3Uploader,
        mock_s3_client: MagicMock,
    ) -> None:
        """Basarili upload S3 URL'i dondurur."""
        data = b"fake image data"
        key = "screenshots/test.png"

        result = s3_uploader._upload_bytes_sync(data, key, "image/png")

        assert result == "https://test-bucket.s3.eu-west-1.amazonaws.com/screenshots/test.png"
        mock_s3_client.put_object.assert_called_once_with(
            Bucket="test-bucket",
            Key="screenshots/test.png",
            Body=data,
            ContentType="image/png",
        )

    def test_upload_failure_raises_error(
        self,
        s3_uploader: S3Uploader,
        mock_s3_client: MagicMock,
    ) -> None:
        """Upload basarisiz olursa S3UploadError firlatir."""
        mock_s3_client.put_object.side_effect = Exception("Access Denied")

        with pytest.raises(S3UploadError, match="S3 upload basarisiz"):
            s3_uploader._upload_bytes_sync(b"data", "key.png", "image/png")


# --- upload_bytes (async) Tests ---


class TestUploadBytes:
    """S3Uploader.upload_bytes async testleri."""

    async def test_async_upload_returns_url(
        self,
        s3_uploader: S3Uploader,
    ) -> None:
        """Asenkron upload S3 URL'i dondurur."""
        result = await s3_uploader.upload_bytes(
            data=b"fake image data",
            key="screenshots/async-test.png",
        )

        assert "test-bucket.s3.eu-west-1.amazonaws.com" in result
        assert "screenshots/async-test.png" in result

    async def test_async_upload_with_custom_content_type(
        self,
        s3_uploader: S3Uploader,
        mock_s3_client: MagicMock,
    ) -> None:
        """Ozel content type ile upload."""
        await s3_uploader.upload_bytes(
            data=b"log data",
            key="logs/test.txt",
            content_type="text/plain",
        )

        mock_s3_client.put_object.assert_called_once_with(
            Bucket="test-bucket",
            Key="logs/test.txt",
            Body=b"log data",
            ContentType="text/plain",
        )

    async def test_async_upload_failure_raises_error(
        self,
        s3_uploader: S3Uploader,
        mock_s3_client: MagicMock,
    ) -> None:
        """Asenkron upload basarisizsa S3UploadError firlatir."""
        mock_s3_client.put_object.side_effect = Exception("Network error")

        with pytest.raises(S3UploadError, match="S3 upload basarisiz"):
            await s3_uploader.upload_bytes(
                data=b"data",
                key="key.png",
            )


# --- bytes_to_base64 Tests ---


class TestBytesToBase64:
    """bytes_to_base64 fonksiyon testleri."""

    def test_encodes_bytes_to_base64(self) -> None:
        """Byte verisi base64 string'e donusturulur."""
        data = b"Hello, World!"
        result = bytes_to_base64(data)
        assert result == base64.b64encode(data).decode("utf-8")

    def test_empty_bytes_returns_empty_base64(self) -> None:
        """Bos byte verisi bos base64 dondurur."""
        result = bytes_to_base64(b"")
        assert result == ""

    def test_round_trip_encoding(self) -> None:
        """Encode/decode round trip dogru calisiyor."""
        original = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        encoded = bytes_to_base64(original)
        decoded = base64.b64decode(encoded)
        assert decoded == original
