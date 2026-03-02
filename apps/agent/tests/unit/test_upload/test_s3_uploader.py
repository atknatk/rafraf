"""Unit tests for S3Uploader - basic smoke tests."""

from __future__ import annotations

import base64
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.upload.s3_uploader import (
    ALLOWED_EXTENSIONS,
    FileValidationError,
    RetryConfig,
    RetryExhaustedError,
    S3Config,
    S3UploadError,
    S3Uploader,
    UploadProgress,
    UploadResult,
    UploadStatus,
    build_s3_key,
    bytes_to_base64,
    detect_content_type,
)


# --- Fixtures ---


@pytest.fixture
def s3_config() -> S3Config:
    """Test icin S3Config olusturur."""
    return S3Config(
        bucket="test-bucket",
        region="eu-west-1",
        retry=RetryConfig(max_retries=2, initial_delay=0.01),
    )


@pytest.fixture
def mock_s3_client() -> AsyncMock:
    """Mock aioboto3 S3 client olusturur."""
    client = AsyncMock()
    client.put_object = AsyncMock(return_value={"ResponseMetadata": {"HTTPStatusCode": 200}})
    client.create_multipart_upload = AsyncMock(return_value={"UploadId": "test-upload-id"})
    client.upload_part = AsyncMock(return_value={"ETag": '"test-etag"'})
    client.complete_multipart_upload = AsyncMock(return_value={})
    client.abort_multipart_upload = AsyncMock(return_value={})
    client.generate_presigned_url = AsyncMock(
        return_value="https://test-bucket.s3.amazonaws.com/key?signed=true",
    )
    client.close = AsyncMock()
    return client


@pytest.fixture
def s3_uploader(s3_config: S3Config, mock_s3_client: AsyncMock) -> S3Uploader:
    """Test icin S3Uploader instance olusturur."""
    return S3Uploader(
        config=s3_config,
        client=mock_s3_client,
    )


# --- S3Config Tests ---


class TestS3Config:
    """S3Config testleri."""

    def test_create_with_defaults(self) -> None:
        """Varsayilan parametreler ile olusturulur."""
        config = S3Config(bucket="my-bucket")
        assert config.bucket == "my-bucket"
        assert config.region == "eu-west-1"
        assert config.max_file_size == 100 * 1024 * 1024
        assert config.multipart_threshold == 10 * 1024 * 1024
        assert config.multipart_chunk_size == 10 * 1024 * 1024

    def test_create_with_custom_values(self) -> None:
        """Ozel degerler ile olusturulur."""
        config = S3Config(
            bucket="custom-bucket",
            region="us-east-1",
            max_file_size=50 * 1024 * 1024,
        )
        assert config.bucket == "custom-bucket"
        assert config.region == "us-east-1"
        assert config.max_file_size == 50 * 1024 * 1024


# --- S3Uploader Init Tests ---


class TestS3UploaderInit:
    """S3Uploader __init__ testleri."""

    def test_create_with_config(self, s3_config: S3Config) -> None:
        """Config ile olusturulur."""
        uploader = S3Uploader(config=s3_config)
        assert uploader.config.bucket == "test-bucket"
        assert uploader._client is None

    def test_create_with_injected_client(
        self,
        s3_config: S3Config,
        mock_s3_client: AsyncMock,
    ) -> None:
        """Enjekte edilen client kullanilir."""
        uploader = S3Uploader(config=s3_config, client=mock_s3_client)
        assert uploader._client is mock_s3_client


# --- _get_client Tests ---


class TestGetClient:
    """S3Uploader._get_client testleri."""

    async def test_returns_injected_client(
        self,
        s3_uploader: S3Uploader,
        mock_s3_client: AsyncMock,
    ) -> None:
        """Enjekte edilen client dondurulur."""
        client = await s3_uploader._get_client()
        assert client is mock_s3_client

    async def test_raises_error_if_aioboto3_not_installed(
        self,
        s3_config: S3Config,
    ) -> None:
        """aioboto3 yuklu degilse S3UploadError firlatir."""
        uploader = S3Uploader(config=s3_config)

        with patch.dict("sys.modules", {"aioboto3": None}):
            with pytest.raises(S3UploadError, match="aioboto3 yuklu degil"):
                await uploader._get_client()


# --- validate_bytes Tests ---


class TestValidateBytes:
    """S3Uploader.validate_bytes testleri."""

    def test_valid_bytes(self, s3_uploader: S3Uploader) -> None:
        """Gecerli byte verisi boyutu dondurur."""
        size = s3_uploader.validate_bytes(b"test data")
        assert size == 9

    def test_empty_bytes_raises_error(self, s3_uploader: S3Uploader) -> None:
        """Bos veri hata firlatir."""
        with pytest.raises(FileValidationError, match="Veri bos"):
            s3_uploader.validate_bytes(b"")

    def test_oversized_bytes_raises_error(self, s3_config: S3Config) -> None:
        """Boyut sinirini asan veri hata firlatir."""
        config = S3Config(bucket="test", max_file_size=10)
        uploader = S3Uploader(config=config, client=AsyncMock())
        with pytest.raises(FileValidationError, match="siniri asildi"):
            uploader.validate_bytes(b"x" * 20)


# --- validate_file Tests ---


class TestValidateFile:
    """S3Uploader.validate_file testleri."""

    def test_valid_file(self, s3_uploader: S3Uploader, tmp_path: Path) -> None:
        """Gecerli dosya boyut ve content type dondurur."""
        test_file = tmp_path / "test.png"
        test_file.write_bytes(b"\x89PNG" + b"\x00" * 100)
        size, content_type = s3_uploader.validate_file(test_file)
        assert size > 0
        assert content_type == "image/png"

    def test_missing_file_raises_error(self, s3_uploader: S3Uploader) -> None:
        """Var olmayan dosya hata firlatir."""
        with pytest.raises(FileValidationError, match="Dosya bulunamadi"):
            s3_uploader.validate_file(Path("/nonexistent/file.png"))

    def test_empty_file_raises_error(
        self,
        s3_uploader: S3Uploader,
        tmp_path: Path,
    ) -> None:
        """Bos dosya hata firlatir."""
        test_file = tmp_path / "empty.png"
        test_file.write_bytes(b"")
        with pytest.raises(FileValidationError, match="Dosya bos"):
            s3_uploader.validate_file(test_file)

    def test_unsupported_extension_raises_error(
        self,
        s3_uploader: S3Uploader,
        tmp_path: Path,
    ) -> None:
        """Desteklenmeyen dosya uzantisi hata firlatir."""
        test_file = tmp_path / "test.exe"
        test_file.write_bytes(b"binary data")
        with pytest.raises(FileValidationError, match="desteklenmiyor"):
            s3_uploader.validate_file(test_file)

    def test_oversized_file_raises_error(self, tmp_path: Path) -> None:
        """Boyut sinirini asan dosya hata firlatir."""
        config = S3Config(bucket="test", max_file_size=10)
        uploader = S3Uploader(config=config, client=AsyncMock())
        test_file = tmp_path / "big.png"
        test_file.write_bytes(b"x" * 20)
        with pytest.raises(FileValidationError, match="siniri asildi"):
            uploader.validate_file(test_file)


# --- Single Upload Tests ---


class TestSingleUpload:
    """S3Uploader._single_upload testleri."""

    async def test_successful_upload_returns_url(
        self,
        s3_uploader: S3Uploader,
        mock_s3_client: AsyncMock,
    ) -> None:
        """Basarili upload S3 URL'i dondurur."""
        result = await s3_uploader._single_upload(
            b"test data",
            "screenshots/test.png",
            "image/png",
        )
        assert "test-bucket.s3.eu-west-1.amazonaws.com" in result
        assert "screenshots/test.png" in result
        mock_s3_client.put_object.assert_called_once()

    async def test_upload_failure_raises_error(
        self,
        s3_uploader: S3Uploader,
        mock_s3_client: AsyncMock,
    ) -> None:
        """Upload basarisizsa S3UploadError firlatir."""
        mock_s3_client.put_object.side_effect = Exception("Access Denied")
        with pytest.raises(S3UploadError, match="S3 upload basarisiz"):
            await s3_uploader._single_upload(b"data", "key.png", "image/png")

    async def test_progress_callback_called(
        self,
        s3_uploader: S3Uploader,
    ) -> None:
        """Progress callback cagrilir."""
        progress_events: list[UploadProgress] = []
        await s3_uploader._single_upload(
            b"test data",
            "key.png",
            "image/png",
            progress_callback=progress_events.append,
        )
        assert len(progress_events) == 2
        assert progress_events[0].status == UploadStatus.IN_PROGRESS
        assert progress_events[1].status == UploadStatus.COMPLETED
        assert progress_events[1].percentage == 100.0


# --- upload_bytes (async) Tests ---


class TestUploadBytes:
    """S3Uploader.upload_bytes async testleri."""

    async def test_upload_returns_result(
        self,
        s3_uploader: S3Uploader,
    ) -> None:
        """Upload UploadResult dondurur."""
        result = await s3_uploader.upload_bytes(
            data=b"fake image data",
            key="screenshots/async-test.png",
        )
        assert isinstance(result, UploadResult)
        assert "test-bucket" in result.url
        assert result.key == "screenshots/async-test.png"
        assert result.bucket == "test-bucket"
        assert result.multipart is False

    async def test_upload_with_custom_content_type(
        self,
        s3_uploader: S3Uploader,
        mock_s3_client: AsyncMock,
    ) -> None:
        """Ozel content type ile upload."""
        result = await s3_uploader.upload_bytes(
            data=b"log data",
            key="logs/test.txt",
            content_type="text/plain",
        )
        assert result.content_type == "text/plain"

    async def test_upload_failure_raises_error(
        self,
        s3_uploader: S3Uploader,
        mock_s3_client: AsyncMock,
    ) -> None:
        """Upload basarisizsa hata firlatir."""
        mock_s3_client.put_object.side_effect = Exception("Network error")
        with pytest.raises(RetryExhaustedError):
            await s3_uploader.upload_bytes(data=b"data", key="key.png")


# --- Multipart Upload Tests ---


class TestMultipartUpload:
    """Multipart upload testleri."""

    async def test_multipart_triggered_for_large_data(
        self,
        mock_s3_client: AsyncMock,
    ) -> None:
        """Buyuk veri icin multipart upload tetiklenir."""
        config = S3Config(
            bucket="test-bucket",
            multipart_threshold=100,
            multipart_chunk_size=50,
            retry=RetryConfig(max_retries=1, initial_delay=0.01),
        )
        uploader = S3Uploader(config=config, client=mock_s3_client)

        result = await uploader.upload_bytes(
            data=b"x" * 200,
            key="large-file.zip",
            content_type="application/zip",
        )
        assert result.multipart is True
        mock_s3_client.create_multipart_upload.assert_called_once()
        assert mock_s3_client.upload_part.call_count == 4  # 200/50 = 4 parts
        mock_s3_client.complete_multipart_upload.assert_called_once()

    async def test_multipart_abort_on_failure(
        self,
        mock_s3_client: AsyncMock,
    ) -> None:
        """Hata durumunda multipart upload iptal edilir."""
        config = S3Config(
            bucket="test-bucket",
            multipart_threshold=100,
            multipart_chunk_size=50,
            retry=RetryConfig(max_retries=1, initial_delay=0.01),
        )
        uploader = S3Uploader(config=config, client=mock_s3_client)
        mock_s3_client.upload_part.side_effect = Exception("Network error")

        with pytest.raises(RetryExhaustedError):
            await uploader.upload_bytes(data=b"x" * 200, key="fail.zip")

        mock_s3_client.abort_multipart_upload.assert_called()


# --- Pre-signed URL Tests ---


class TestPresignedUrl:
    """Pre-signed URL testleri."""

    async def test_generate_get_url(
        self,
        s3_uploader: S3Uploader,
        mock_s3_client: AsyncMock,
    ) -> None:
        """GET pre-signed URL olusturulur."""
        url = await s3_uploader.generate_presigned_url("screenshots/test.png")
        assert "signed=true" in url
        mock_s3_client.generate_presigned_url.assert_called_once()

    async def test_generate_put_url(
        self,
        s3_uploader: S3Uploader,
        mock_s3_client: AsyncMock,
    ) -> None:
        """PUT pre-signed URL olusturulur."""
        url = await s3_uploader.generate_presigned_url(
            "uploads/new-file.png",
            http_method="PUT",
        )
        assert url
        call_kwargs = mock_s3_client.generate_presigned_url.call_args
        assert call_kwargs[1]["ClientMethod"] == "put_object" or call_kwargs[0][0] == "put_object"

    async def test_presigned_url_failure_raises_error(
        self,
        s3_uploader: S3Uploader,
        mock_s3_client: AsyncMock,
    ) -> None:
        """URL olusturma basarisizsa hata firlatir."""
        mock_s3_client.generate_presigned_url.side_effect = Exception("Access Denied")
        with pytest.raises(S3UploadError, match="Pre-signed URL"):
            await s3_uploader.generate_presigned_url("key.png")


# --- Retry Tests ---


class TestRetry:
    """Retry mekanizmasi testleri."""

    async def test_retry_on_transient_error(
        self,
        mock_s3_client: AsyncMock,
    ) -> None:
        """Gecici hata sonrasi retry basarili olur."""
        config = S3Config(
            bucket="test-bucket",
            retry=RetryConfig(max_retries=3, initial_delay=0.01),
        )
        uploader = S3Uploader(config=config, client=mock_s3_client)

        # Ilk cagri basarisiz, ikinci basarili
        mock_s3_client.put_object.side_effect = [
            Exception("Timeout"),
            {"ResponseMetadata": {"HTTPStatusCode": 200}},
        ]

        result = await uploader.upload_bytes(data=b"test", key="retry-test.png")
        assert isinstance(result, UploadResult)
        assert mock_s3_client.put_object.call_count == 2

    async def test_retry_exhausted_raises_error(
        self,
        mock_s3_client: AsyncMock,
    ) -> None:
        """Tum retry denemeleri basarisiz olursa hata firlatir."""
        config = S3Config(
            bucket="test-bucket",
            retry=RetryConfig(max_retries=2, initial_delay=0.01),
        )
        uploader = S3Uploader(config=config, client=mock_s3_client)
        mock_s3_client.put_object.side_effect = Exception("Persistent error")

        with pytest.raises(RetryExhaustedError, match="2 denemeden sonra basarisiz"):
            await uploader.upload_bytes(data=b"test", key="fail.png")


# --- File Upload Tests ---


class TestUploadFile:
    """S3Uploader.upload_file testleri."""

    async def test_upload_file_success(
        self,
        s3_uploader: S3Uploader,
        tmp_path: Path,
    ) -> None:
        """Dosya basarili sekilde yuklenir."""
        test_file = tmp_path / "test.png"
        test_file.write_bytes(b"\x89PNG" + b"\x00" * 100)

        result = await s3_uploader.upload_file(test_file, "screenshots/test.png")
        assert isinstance(result, UploadResult)
        assert result.content_type == "image/png"

    async def test_upload_file_validation_error(
        self,
        s3_uploader: S3Uploader,
    ) -> None:
        """Gecersiz dosya hata firlatir."""
        with pytest.raises(FileValidationError):
            await s3_uploader.upload_file(Path("/nonexistent.png"), "key.png")


# --- Close Tests ---


class TestClose:
    """S3Uploader.close testleri."""

    async def test_close_client(
        self,
        s3_uploader: S3Uploader,
        mock_s3_client: AsyncMock,
    ) -> None:
        """Client kapatilir."""
        await s3_uploader.close()
        mock_s3_client.close.assert_called_once()
        assert s3_uploader._client is None

    async def test_close_without_client(self, s3_config: S3Config) -> None:
        """Client yokken close hata vermez."""
        uploader = S3Uploader(config=s3_config)
        await uploader.close()  # Hata firlatmamali


# --- Helper Function Tests ---


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


class TestDetectContentType:
    """detect_content_type testleri."""

    def test_png_detection(self) -> None:
        """PNG dosya tipi tespit edilir."""
        assert detect_content_type("test.png") == "image/png"

    def test_json_detection(self) -> None:
        """JSON dosya tipi tespit edilir."""
        assert detect_content_type("data.json") == "application/json"

    def test_unknown_returns_default(self) -> None:
        """Bilinmeyen tip icin varsayilan dondurulur."""
        result = detect_content_type("file.unknownext")
        assert result == "application/octet-stream"


class TestBuildS3Key:
    """build_s3_key testleri."""

    def test_basic_key(self) -> None:
        """Temel key olusturulur."""
        key = build_s3_key("screenshots", "test.png")
        assert key == "screenshots/test.png"

    def test_key_with_host_id(self) -> None:
        """Host ID ile key olusturulur."""
        key = build_s3_key("screenshots", "test.png", host_id="macbook-pro")
        assert key == "screenshots/macbook-pro/test.png"

    def test_key_strips_path(self) -> None:
        """Dosya yolundan sadece dosya adi alinir."""
        key = build_s3_key("logs", "/tmp/some/path/output.log")
        assert key == "logs/output.log"
