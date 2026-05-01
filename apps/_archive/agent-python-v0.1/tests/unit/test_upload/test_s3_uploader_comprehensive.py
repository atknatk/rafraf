"""Comprehensive tests for S3Uploader - tester agent tarafindan yazildi.

Multipart upload, pre-signed URL, progress callback, retry mekanizmasi,
dosya dogrulama edge case'leri ve yardimci fonksiyon testlerini kapsar.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

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
    return S3Uploader(config=s3_config, client=mock_s3_client)


# --- S3Config Edge Cases ---


class TestS3ConfigEdgeCases:
    """S3Config edge case testleri."""

    def test_default_retry_config(self) -> None:
        """Varsayilan retry config degerleri dogru."""
        config = S3Config(bucket="test")
        assert config.retry.max_retries == 3
        assert config.retry.initial_delay == 1.0
        assert config.retry.backoff_factor == 2.0
        assert config.retry.max_delay == 30.0

    def test_custom_retry_config(self) -> None:
        """Ozel retry config uygulanir."""
        retry = RetryConfig(max_retries=5, initial_delay=0.5, backoff_factor=3.0, max_delay=60.0)
        config = S3Config(bucket="test", retry=retry)
        assert config.retry.max_retries == 5
        assert config.retry.backoff_factor == 3.0

    def test_default_allowed_extensions(self) -> None:
        """Varsayilan izinli uzantilar dogru."""
        config = S3Config(bucket="test")
        assert ".png" in config.allowed_extensions
        assert ".jpg" in config.allowed_extensions
        assert ".log" in config.allowed_extensions
        assert ".json" in config.allowed_extensions
        assert ".exe" not in config.allowed_extensions

    def test_custom_allowed_extensions(self) -> None:
        """Ozel uzanti seti uygulanir."""
        extensions = frozenset({".png", ".jpg"})
        config = S3Config(bucket="test", allowed_extensions=extensions)
        assert config.allowed_extensions == extensions
        assert ".log" not in config.allowed_extensions

    def test_default_presigned_expiry(self) -> None:
        """Varsayilan pre-signed URL suresi 1 saat."""
        config = S3Config(bucket="test")
        assert config.presigned_expiry == 3600

    def test_config_property(self, s3_uploader: S3Uploader) -> None:
        """Config property dogru dondurulur."""
        assert s3_uploader.config.bucket == "test-bucket"
        assert s3_uploader.config.region == "eu-west-1"


# --- UploadProgress Model Tests ---


class TestUploadProgressModel:
    """UploadProgress frozen dataclass testleri."""

    def test_create_progress(self) -> None:
        """UploadProgress olusturulur."""
        progress = UploadProgress(
            bytes_sent=50,
            total_bytes=100,
            percentage=50.0,
            status=UploadStatus.IN_PROGRESS,
        )
        assert progress.bytes_sent == 50
        assert progress.percentage == 50.0
        assert progress.part_number == 0
        assert progress.total_parts == 0

    def test_frozen_dataclass(self) -> None:
        """UploadProgress immutable (frozen)."""
        progress = UploadProgress(
            bytes_sent=0,
            total_bytes=100,
            percentage=0.0,
            status=UploadStatus.PENDING,
        )
        with pytest.raises(AttributeError):
            progress.bytes_sent = 50  # type: ignore[misc]

    def test_multipart_fields(self) -> None:
        """Multipart alanlari dogru."""
        progress = UploadProgress(
            bytes_sent=100,
            total_bytes=300,
            percentage=33.3,
            status=UploadStatus.IN_PROGRESS,
            part_number=1,
            total_parts=3,
        )
        assert progress.part_number == 1
        assert progress.total_parts == 3


# --- UploadResult Model Tests ---


class TestUploadResultModel:
    """UploadResult frozen dataclass testleri."""

    def test_create_result(self) -> None:
        """UploadResult olusturulur."""
        result = UploadResult(
            url="https://bucket.s3.amazonaws.com/key.png",
            key="key.png",
            bucket="bucket",
            size_bytes=1024,
            content_type="image/png",
            multipart=False,
        )
        assert result.url == "https://bucket.s3.amazonaws.com/key.png"
        assert result.multipart is False

    def test_frozen_dataclass(self) -> None:
        """UploadResult immutable."""
        result = UploadResult(
            url="url",
            key="key",
            bucket="b",
            size_bytes=0,
            content_type="ct",
            multipart=False,
        )
        with pytest.raises(AttributeError):
            result.url = "new"  # type: ignore[misc]


# --- UploadStatus Tests ---


class TestUploadStatus:
    """UploadStatus enum testleri."""

    def test_status_values(self) -> None:
        """Status degerleri dogru."""
        assert UploadStatus.PENDING == "pending"
        assert UploadStatus.IN_PROGRESS == "in_progress"
        assert UploadStatus.COMPLETED == "completed"
        assert UploadStatus.FAILED == "failed"

    def test_status_is_string(self) -> None:
        """StrEnum string olarak kullanilabilir."""
        status = UploadStatus.IN_PROGRESS
        assert isinstance(status, str)
        assert status == "in_progress"


# --- Validate File Edge Cases ---


class TestValidateFileEdgeCases:
    """validate_file edge case testleri."""

    def test_directory_instead_of_file(
        self,
        s3_uploader: S3Uploader,
        tmp_path: Path,
    ) -> None:
        """Dizin dosya olarak reddedilir."""
        with pytest.raises(FileValidationError, match="dosya degil"):
            s3_uploader.validate_file(tmp_path)

    def test_file_at_exact_size_limit(
        self,
        tmp_path: Path,
    ) -> None:
        """Tam sinirdaki dosya kabul edilir."""
        config = S3Config(bucket="test", max_file_size=100)
        uploader = S3Uploader(config=config, client=AsyncMock())
        test_file = tmp_path / "exact.png"
        test_file.write_bytes(b"x" * 100)
        size, _ = uploader.validate_file(test_file)
        assert size == 100

    def test_file_one_byte_over_limit(
        self,
        tmp_path: Path,
    ) -> None:
        """Siniri 1 byte asan dosya reddedilir."""
        config = S3Config(bucket="test", max_file_size=100)
        uploader = S3Uploader(config=config, client=AsyncMock())
        test_file = tmp_path / "over.png"
        test_file.write_bytes(b"x" * 101)
        with pytest.raises(FileValidationError, match="siniri asildi"):
            uploader.validate_file(test_file)

    def test_all_allowed_extensions_accepted(self, tmp_path: Path) -> None:
        """Tum izinli uzantilar kabul edilir."""
        config = S3Config(bucket="test")
        uploader = S3Uploader(config=config, client=AsyncMock())

        for ext in ALLOWED_EXTENSIONS:
            test_file = tmp_path / f"test{ext}"
            test_file.write_bytes(b"content")
            size, _ = uploader.validate_file(test_file)
            assert size > 0

    def test_uppercase_extension_rejected(
        self,
        s3_uploader: S3Uploader,
        tmp_path: Path,
    ) -> None:
        """Buyuk harfli uzanti (dot lower sonrasi) kabul edilir."""
        test_file = tmp_path / "test.PNG"
        test_file.write_bytes(b"content")
        size, _ = s3_uploader.validate_file(test_file)
        assert size > 0

    def test_content_type_detection(
        self,
        s3_uploader: S3Uploader,
        tmp_path: Path,
    ) -> None:
        """Dosya tipinden content type dogru tespit edilir."""
        test_cases = {
            "test.png": "image/png",
            "test.jpg": "image/jpeg",
            "test.json": "application/json",
            "test.txt": "text/plain",
        }
        for filename, expected_type in test_cases.items():
            test_file = tmp_path / filename
            test_file.write_bytes(b"data")
            _, content_type = s3_uploader.validate_file(test_file)
            assert content_type == expected_type, (
                f"{filename}: expected {expected_type}, got {content_type}"
            )


# --- Validate Bytes Edge Cases ---


class TestValidateBytesEdgeCases:
    """validate_bytes edge case testleri."""

    def test_single_byte(self, s3_uploader: S3Uploader) -> None:
        """1 byte veri kabul edilir."""
        size = s3_uploader.validate_bytes(b"x")
        assert size == 1

    def test_bytes_at_exact_limit(self) -> None:
        """Tam sinirdaki veri kabul edilir."""
        config = S3Config(bucket="test", max_file_size=50)
        uploader = S3Uploader(config=config, client=AsyncMock())
        size = uploader.validate_bytes(b"x" * 50)
        assert size == 50

    def test_bytes_one_over_limit(self) -> None:
        """Siniri 1 byte asan veri reddedilir."""
        config = S3Config(bucket="test", max_file_size=50)
        uploader = S3Uploader(config=config, client=AsyncMock())
        with pytest.raises(FileValidationError, match="siniri asildi"):
            uploader.validate_bytes(b"x" * 51)


# --- Single Upload Progress Tests ---


class TestSingleUploadProgress:
    """Single upload progress callback detayli testleri."""

    async def test_progress_on_failure(
        self,
        s3_uploader: S3Uploader,
        mock_s3_client: AsyncMock,
    ) -> None:
        """Hata durumunda FAILED status raporlanir."""
        mock_s3_client.put_object.side_effect = Exception("Network error")
        progress_events: list[UploadProgress] = []

        with pytest.raises(S3UploadError):
            await s3_uploader._single_upload(
                b"data",
                "key.png",
                "image/png",
                progress_callback=progress_events.append,
            )

        assert len(progress_events) == 2
        assert progress_events[0].status == UploadStatus.IN_PROGRESS
        assert progress_events[1].status == UploadStatus.FAILED

    async def test_no_callback_no_error(
        self,
        s3_uploader: S3Uploader,
    ) -> None:
        """Callback verilmediginde hata olmaz."""
        url = await s3_uploader._single_upload(
            b"data",
            "key.png",
            "image/png",
            progress_callback=None,
        )
        assert "key.png" in url


# --- Multipart Upload Edge Cases ---


class TestMultipartUploadEdgeCases:
    """Multipart upload edge case testleri."""

    async def test_multipart_progress_tracking(
        self,
        mock_s3_client: AsyncMock,
    ) -> None:
        """Multipart progress dogru izlenir."""
        config = S3Config(
            bucket="test-bucket",
            multipart_threshold=50,
            multipart_chunk_size=50,
            retry=RetryConfig(max_retries=1, initial_delay=0.01),
        )
        uploader = S3Uploader(config=config, client=mock_s3_client)
        progress_events: list[UploadProgress] = []

        await uploader.upload_bytes(
            data=b"x" * 150,
            key="multi.zip",
            progress_callback=progress_events.append,
        )

        # Baslangic (0%) + 3 part + tamamlanma (100%)
        assert len(progress_events) == 5
        assert progress_events[0].percentage == 0.0
        assert progress_events[0].status == UploadStatus.IN_PROGRESS
        assert progress_events[0].total_parts == 3

        # Her part ilerliyor
        assert progress_events[1].part_number == 1
        assert progress_events[2].part_number == 2
        assert progress_events[3].part_number == 3

        # Tamamlanma
        assert progress_events[4].percentage == 100.0
        assert progress_events[4].status == UploadStatus.COMPLETED

    async def test_multipart_below_threshold_uses_single(
        self,
        s3_uploader: S3Uploader,
        mock_s3_client: AsyncMock,
    ) -> None:
        """Esik altinda single upload kullanilir."""
        result = await s3_uploader.upload_bytes(data=b"small data", key="small.txt")
        assert result.multipart is False
        mock_s3_client.put_object.assert_called_once()
        mock_s3_client.create_multipart_upload.assert_not_called()

    async def test_multipart_at_threshold_uses_multipart(
        self,
        mock_s3_client: AsyncMock,
    ) -> None:
        """Tam esikteki veri multipart kullanir."""
        config = S3Config(
            bucket="test-bucket",
            multipart_threshold=100,
            multipart_chunk_size=100,
            retry=RetryConfig(max_retries=1, initial_delay=0.01),
        )
        uploader = S3Uploader(config=config, client=mock_s3_client)
        result = await uploader.upload_bytes(data=b"x" * 100, key="exact.zip")
        assert result.multipart is True
        mock_s3_client.create_multipart_upload.assert_called_once()

    async def test_multipart_uneven_chunks(
        self,
        mock_s3_client: AsyncMock,
    ) -> None:
        """Esit bolunmeyen veri icin son parca dogru boyutta."""
        config = S3Config(
            bucket="test-bucket",
            multipart_threshold=100,
            multipart_chunk_size=70,
            retry=RetryConfig(max_retries=1, initial_delay=0.01),
        )
        uploader = S3Uploader(config=config, client=mock_s3_client)
        await uploader.upload_bytes(data=b"x" * 150, key="uneven.zip")
        # 150 / 70 = 2.14 -> 3 parts (70 + 70 + 10)
        assert mock_s3_client.upload_part.call_count == 3

    async def test_multipart_failure_progress(
        self,
        mock_s3_client: AsyncMock,
    ) -> None:
        """Multipart hata durumunda FAILED progress raporlanir."""
        config = S3Config(
            bucket="test-bucket",
            multipart_threshold=50,
            multipart_chunk_size=50,
            retry=RetryConfig(max_retries=1, initial_delay=0.01),
        )
        uploader = S3Uploader(config=config, client=mock_s3_client)
        mock_s3_client.upload_part.side_effect = Exception("Part upload failed")

        progress_events: list[UploadProgress] = []

        with pytest.raises(RetryExhaustedError):
            await uploader.upload_bytes(
                data=b"x" * 100,
                key="fail.zip",
                progress_callback=progress_events.append,
            )

        # Son event FAILED olmali
        failed_events = [e for e in progress_events if e.status == UploadStatus.FAILED]
        assert len(failed_events) >= 1

    async def test_multipart_abort_failure_logged_not_raised(
        self,
        mock_s3_client: AsyncMock,
    ) -> None:
        """Abort basarisiz olsa bile ana hata firlatilir."""
        config = S3Config(
            bucket="test-bucket",
            multipart_threshold=50,
            multipart_chunk_size=50,
            retry=RetryConfig(max_retries=1, initial_delay=0.01),
        )
        uploader = S3Uploader(config=config, client=mock_s3_client)
        mock_s3_client.upload_part.side_effect = Exception("Part failed")
        mock_s3_client.abort_multipart_upload.side_effect = Exception("Abort also failed")

        with pytest.raises(RetryExhaustedError):
            await uploader.upload_bytes(data=b"x" * 100, key="fail.zip")

    async def test_multipart_complete_params(
        self,
        mock_s3_client: AsyncMock,
    ) -> None:
        """complete_multipart_upload dogru parametrelerle cagirilir."""
        config = S3Config(
            bucket="test-bucket",
            multipart_threshold=50,
            multipart_chunk_size=50,
            retry=RetryConfig(max_retries=1, initial_delay=0.01),
        )
        uploader = S3Uploader(config=config, client=mock_s3_client)
        await uploader.upload_bytes(data=b"x" * 100, key="parts.zip")

        call_kwargs = mock_s3_client.complete_multipart_upload.call_args[1]
        assert call_kwargs["Bucket"] == "test-bucket"
        assert call_kwargs["Key"] == "parts.zip"
        assert call_kwargs["UploadId"] == "test-upload-id"
        assert len(call_kwargs["MultipartUpload"]["Parts"]) == 2


# --- Retry Edge Cases ---


class TestRetryEdgeCases:
    """Retry mekanizmasi edge case testleri."""

    async def test_retry_succeeds_on_second_attempt(
        self,
        mock_s3_client: AsyncMock,
    ) -> None:
        """Ikinci denemede basarili."""
        config = S3Config(
            bucket="test-bucket",
            retry=RetryConfig(max_retries=3, initial_delay=0.01),
        )
        uploader = S3Uploader(config=config, client=mock_s3_client)
        mock_s3_client.put_object.side_effect = [
            Exception("Timeout"),
            {"ResponseMetadata": {"HTTPStatusCode": 200}},
        ]

        result = await uploader.upload_bytes(data=b"test", key="retry.png")
        assert isinstance(result, UploadResult)

    async def test_retry_succeeds_on_last_attempt(
        self,
        mock_s3_client: AsyncMock,
    ) -> None:
        """Son denemede basarili."""
        config = S3Config(
            bucket="test-bucket",
            retry=RetryConfig(max_retries=3, initial_delay=0.01),
        )
        uploader = S3Uploader(config=config, client=mock_s3_client)
        mock_s3_client.put_object.side_effect = [
            Exception("Error 1"),
            Exception("Error 2"),
            {"ResponseMetadata": {"HTTPStatusCode": 200}},
        ]

        result = await uploader.upload_bytes(data=b"test", key="retry-last.png")
        assert isinstance(result, UploadResult)
        assert mock_s3_client.put_object.call_count == 3

    async def test_retry_with_single_retry_config(
        self,
        mock_s3_client: AsyncMock,
    ) -> None:
        """max_retries=1 durumunda retry yapilmaz."""
        config = S3Config(
            bucket="test-bucket",
            retry=RetryConfig(max_retries=1, initial_delay=0.01),
        )
        uploader = S3Uploader(config=config, client=mock_s3_client)
        mock_s3_client.put_object.side_effect = Exception("Error")

        with pytest.raises(RetryExhaustedError, match="1 denemeden sonra"):
            await uploader.upload_bytes(data=b"test", key="no-retry.png")

    async def test_file_validation_error_not_retried(
        self,
        s3_uploader: S3Uploader,
    ) -> None:
        """FileValidationError retry yapilmadan firlatilir."""
        with pytest.raises(FileValidationError, match="Veri bos"):
            await s3_uploader.upload_bytes(data=b"", key="empty.png")

    async def test_retry_multipart_upload(
        self,
        mock_s3_client: AsyncMock,
    ) -> None:
        """Multipart upload da retry edilir."""
        config = S3Config(
            bucket="test-bucket",
            multipart_threshold=50,
            multipart_chunk_size=50,
            retry=RetryConfig(max_retries=3, initial_delay=0.01),
        )
        uploader = S3Uploader(config=config, client=mock_s3_client)

        # Ilk denemede upload_part basarisiz, ikinci denemede basarili
        mock_s3_client.upload_part.side_effect = [
            Exception("First attempt failed"),
            {"ETag": '"etag-1"'},
            {"ETag": '"etag-2"'},
        ]

        result = await uploader.upload_bytes(data=b"x" * 100, key="retry-multi.zip")
        assert result.multipart is True


# --- Pre-signed URL Edge Cases ---


class TestPresignedUrlEdgeCases:
    """Pre-signed URL edge case testleri."""

    async def test_custom_expiry(
        self,
        s3_uploader: S3Uploader,
        mock_s3_client: AsyncMock,
    ) -> None:
        """Ozel gecerlilik suresi uygulanir."""
        await s3_uploader.generate_presigned_url("key.png", expiry=7200)
        call_kwargs = mock_s3_client.generate_presigned_url.call_args[1]
        assert call_kwargs["ExpiresIn"] == 7200

    async def test_default_expiry_from_config(
        self,
        mock_s3_client: AsyncMock,
    ) -> None:
        """Config'den varsayilan gecerlilik suresi alinir."""
        config = S3Config(bucket="test-bucket", presigned_expiry=1800)
        uploader = S3Uploader(config=config, client=mock_s3_client)
        await uploader.generate_presigned_url("key.png")
        call_kwargs = mock_s3_client.generate_presigned_url.call_args[1]
        assert call_kwargs["ExpiresIn"] == 1800

    async def test_zero_expiry(
        self,
        s3_uploader: S3Uploader,
        mock_s3_client: AsyncMock,
    ) -> None:
        """expiry=0 gonderilir (0 gecerli bir int)."""
        await s3_uploader.generate_presigned_url("key.png", expiry=0)
        call_kwargs = mock_s3_client.generate_presigned_url.call_args[1]
        assert call_kwargs["ExpiresIn"] == 0


# --- Upload File Edge Cases ---


class TestUploadFileEdgeCases:
    """upload_file edge case testleri."""

    async def test_string_path_accepted(
        self,
        s3_uploader: S3Uploader,
        tmp_path: Path,
    ) -> None:
        """String yol kabul edilir (Path'e donusturulur)."""
        test_file = tmp_path / "test.txt"
        test_file.write_bytes(b"text content")

        result = await s3_uploader.upload_file(str(test_file), "logs/test.txt")
        assert isinstance(result, UploadResult)
        assert result.content_type == "text/plain"

    async def test_upload_file_with_progress(
        self,
        s3_uploader: S3Uploader,
        tmp_path: Path,
    ) -> None:
        """Dosya upload progress callback ile calisir."""
        test_file = tmp_path / "test.png"
        test_file.write_bytes(b"\x89PNG" + b"\x00" * 50)

        progress_events: list[UploadProgress] = []
        result = await s3_uploader.upload_file(
            test_file,
            "screenshots/test.png",
            progress_callback=progress_events.append,
        )
        assert isinstance(result, UploadResult)
        assert len(progress_events) >= 2

    async def test_upload_various_file_types(
        self,
        s3_uploader: S3Uploader,
        tmp_path: Path,
    ) -> None:
        """Cesitli dosya tipleri yuklenir."""
        file_types = {
            "test.jpg": "image/jpeg",
            "test.json": "application/json",
            "test.txt": "text/plain",
            "test.csv": "text/csv",
            "test.pdf": "application/pdf",
            "test.xml": ("application/xml", "text/xml"),
        }
        for filename, expected in file_types.items():
            test_file = tmp_path / filename
            test_file.write_bytes(b"data content here")
            result = await s3_uploader.upload_file(test_file, f"files/{filename}")
            if isinstance(expected, tuple):
                assert result.content_type in expected, f"{filename}: got {result.content_type}"
            else:
                assert result.content_type == expected, f"{filename}: got {result.content_type}"


# --- Close Edge Cases ---


class TestCloseEdgeCases:
    """close() edge case testleri."""

    async def test_close_exception_swallowed(
        self,
        s3_config: S3Config,
        mock_s3_client: AsyncMock,
    ) -> None:
        """Client close hatasi yutulur."""
        mock_s3_client.close.side_effect = Exception("Close failed")
        uploader = S3Uploader(config=s3_config, client=mock_s3_client)
        await uploader.close()  # Hata firlatmamali
        assert uploader._client is None

    async def test_double_close(
        self,
        s3_uploader: S3Uploader,
        mock_s3_client: AsyncMock,
    ) -> None:
        """Iki kez close cagirildiginda hata olmaz."""
        await s3_uploader.close()
        await s3_uploader.close()
        mock_s3_client.close.assert_called_once()


# --- Helper Functions Edge Cases ---


class TestDetectContentTypeEdgeCases:
    """detect_content_type edge case testleri."""

    def test_various_image_types(self) -> None:
        """Cesitli goruntu tipleri tespit edilir."""
        assert detect_content_type("photo.jpeg") == "image/jpeg"
        assert detect_content_type("icon.gif") == "image/gif"
        assert detect_content_type("graphic.webp") == "image/webp"

    def test_text_types(self) -> None:
        """Metin tipleri tespit edilir."""
        assert detect_content_type("notes.txt") == "text/plain"
        assert detect_content_type("page.html") == "text/html"
        assert detect_content_type("data.csv") == "text/csv"

    def test_archive_types(self) -> None:
        """Arsiv tipleri tespit edilir."""
        assert detect_content_type("archive.zip") == "application/zip"
        assert detect_content_type("backup.tar") == "application/x-tar"
        # .gz mimetypes davranisi platforma bagli olabilir
        result = detect_content_type("compressed.gz")
        assert result in ("application/gzip", "application/octet-stream", "application/x-gzip")

    def test_path_object(self) -> None:
        """Path nesnesi kabul edilir."""
        assert detect_content_type(Path("test.png")) == "image/png"

    def test_no_extension(self) -> None:
        """Uzantisiz dosya varsayilan tip dondurur."""
        result = detect_content_type("Makefile")
        assert result == "application/octet-stream"

    def test_double_extension(self) -> None:
        """Cift uzantili dosya mimetypes tarafindan algilanir."""
        result = detect_content_type("backup.tar.gz")
        # Platform bagimliligi: .tar.gz bazen application/x-tar, bazen application/gzip
        assert result in ("application/gzip", "application/x-tar", "application/x-gzip")


class TestBuildS3KeyEdgeCases:
    """build_s3_key edge case testleri."""

    def test_empty_host_id(self) -> None:
        """Bos host_id eklenez."""
        key = build_s3_key("screenshots", "test.png", host_id="")
        assert key == "screenshots/test.png"

    def test_none_host_id(self) -> None:
        """None host_id eklenmez."""
        key = build_s3_key("screenshots", "test.png", host_id=None)
        assert key == "screenshots/test.png"

    def test_nested_path_stripped(self) -> None:
        """Dosya yolundan sadece dosya adi alinir."""
        key = build_s3_key("logs", "/var/log/app/output.log", host_id="server-1")
        assert key == "logs/server-1/output.log"

    def test_special_characters_preserved(self) -> None:
        """Ozel karakterler korunur."""
        key = build_s3_key("data", "2024-01-01_report.json")
        assert key == "data/2024-01-01_report.json"


# --- Integration-style Tests ---


class TestUploadIntegration:
    """Upload akisi integration testleri (mock ile)."""

    async def test_full_upload_cycle(
        self,
        s3_uploader: S3Uploader,
        mock_s3_client: AsyncMock,
    ) -> None:
        """Tam upload dongusu: validate -> upload -> result."""
        data = b"Test data content"
        result = await s3_uploader.upload_bytes(
            data=data,
            key="artifacts/test.txt",
            content_type="text/plain",
        )

        assert isinstance(result, UploadResult)
        assert result.url == "https://test-bucket.s3.eu-west-1.amazonaws.com/artifacts/test.txt"
        assert result.key == "artifacts/test.txt"
        assert result.bucket == "test-bucket"
        assert result.size_bytes == len(data)
        assert result.content_type == "text/plain"
        assert result.multipart is False

    async def test_upload_then_presigned_url(
        self,
        s3_uploader: S3Uploader,
        mock_s3_client: AsyncMock,
    ) -> None:
        """Upload sonrasi pre-signed URL olusturma."""
        result = await s3_uploader.upload_bytes(data=b"data", key="file.txt")
        presigned = await s3_uploader.generate_presigned_url(result.key)
        assert presigned is not None
        assert isinstance(presigned, str)

    async def test_empty_data_rejected_before_upload(
        self,
        s3_uploader: S3Uploader,
        mock_s3_client: AsyncMock,
    ) -> None:
        """Bos veri upload'a gitmeden reddedilir."""
        with pytest.raises(FileValidationError, match="Veri bos"):
            await s3_uploader.upload_bytes(data=b"", key="empty.txt")

        mock_s3_client.put_object.assert_not_called()


# --- Error Hierarchy Tests ---


class TestErrorHierarchy:
    """Hata sinifi hiyerarsisi testleri."""

    def test_file_validation_error_is_s3_upload_error(self) -> None:
        """FileValidationError, S3UploadError'dan turetilmis."""
        error = FileValidationError("test")
        assert isinstance(error, S3UploadError)

    def test_retry_exhausted_error_is_s3_upload_error(self) -> None:
        """RetryExhaustedError, S3UploadError'dan turetilmis."""
        error = RetryExhaustedError("test")
        assert isinstance(error, S3UploadError)

    def test_s3_upload_error_is_exception(self) -> None:
        """S3UploadError, Exception'dan turetilmis."""
        error = S3UploadError("test")
        assert isinstance(error, Exception)
