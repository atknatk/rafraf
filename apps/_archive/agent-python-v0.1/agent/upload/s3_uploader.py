"""S3 upload yoneticisi - dosya/byte upload, multipart, pre-signed URL, retry.

aioboto3 kullanarak asenkron S3 islemleri gerceklestirir.
Multipart upload (>10MB), pre-signed URL, progress raporlama,
retry mekanizmasi ve dosya tipi/boyut dogrulama destegi.
"""

from __future__ import annotations

import asyncio
import base64
import mimetypes
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from types_aiobotocore_s3 import S3Client as AioS3Client
    from types_aiobotocore_s3.type_defs import CompletedPartTypeDef

logger = structlog.get_logger()

# --- Sabitler ---

_DEFAULT_REGION: str = "eu-west-1"
_DEFAULT_CONTENT_TYPE: str = "application/octet-stream"
_MAX_FILE_SIZE: int = 100 * 1024 * 1024  # 100 MB
_MULTIPART_THRESHOLD: int = 10 * 1024 * 1024  # 10 MB
_MULTIPART_CHUNK_SIZE: int = 10 * 1024 * 1024  # 10 MB
_DEFAULT_MAX_RETRIES: int = 3
_DEFAULT_RETRY_DELAY: float = 1.0
_DEFAULT_PRESIGNED_EXPIRY: int = 3600  # 1 saat

# Izin verilen dosya uzantilari
ALLOWED_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".svg",
        ".bmp",
        ".txt",
        ".log",
        ".json",
        ".xml",
        ".csv",
        ".html",
        ".pdf",
        ".zip",
        ".tar",
        ".gz",
        ".mp4",
        ".mov",
        ".avi",
        ".yml",
        ".yaml",
    },
)


# --- Hata Siniflari ---


class S3UploadError(Exception):
    """S3 upload islemlerine ozel hata sinifi."""


class FileValidationError(S3UploadError):
    """Dosya dogrulama hatalari (boyut, tip, vb.)."""


class RetryExhaustedError(S3UploadError):
    """Tum retry denemeleri tukendikten sonra firlatilir."""


# --- Modeller ---


class UploadStatus(StrEnum):
    """Upload durum degerleri."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class UploadProgress:
    """Upload ilerleme bilgisi.

    Attributes:
        bytes_sent: Simdiye kadar gonderilen byte sayisi.
        total_bytes: Toplam dosya boyutu.
        percentage: Tamamlanma yuzdesi (0-100).
        status: Mevcut upload durumu.
        part_number: Multipart upload icin mevcut parca numarasi.
        total_parts: Multipart upload icin toplam parca sayisi.
    """

    bytes_sent: int
    total_bytes: int
    percentage: float
    status: UploadStatus
    part_number: int = 0
    total_parts: int = 0


@dataclass(frozen=True)
class UploadResult:
    """Upload sonuc bilgisi.

    Attributes:
        url: Yuklenen dosyanin S3 URL'i.
        key: S3 object key.
        bucket: S3 bucket adi.
        size_bytes: Dosya boyutu (byte).
        content_type: MIME content type.
        multipart: Multipart upload kullanilip kullanilmadigi.
    """

    url: str
    key: str
    bucket: str
    size_bytes: int
    content_type: str
    multipart: bool


# Callback tipleri
ProgressCallback = Callable[[UploadProgress], None]


@dataclass
class RetryConfig:
    """Retry konfigurasyonu.

    Attributes:
        max_retries: Maksimum deneme sayisi.
        initial_delay: Ilk bekleme suresi (saniye).
        backoff_factor: Exponential backoff carpani.
        max_delay: Maksimum bekleme suresi (saniye).
    """

    max_retries: int = _DEFAULT_MAX_RETRIES
    initial_delay: float = _DEFAULT_RETRY_DELAY
    backoff_factor: float = 2.0
    max_delay: float = 30.0


@dataclass
class S3Config:
    """S3 upload konfigurasyonu.

    Attributes:
        bucket: S3 bucket adi.
        region: AWS region.
        max_file_size: Maksimum dosya boyutu (byte).
        multipart_threshold: Multipart upload esik degeri (byte).
        multipart_chunk_size: Multipart parca boyutu (byte).
        allowed_extensions: Izin verilen dosya uzantilari.
        retry: Retry konfigurasyonu.
        presigned_expiry: Pre-signed URL gecerlilik suresi (saniye).
    """

    bucket: str
    region: str = _DEFAULT_REGION
    max_file_size: int = _MAX_FILE_SIZE
    multipart_threshold: int = _MULTIPART_THRESHOLD
    multipart_chunk_size: int = _MULTIPART_CHUNK_SIZE
    allowed_extensions: frozenset[str] = field(default_factory=lambda: ALLOWED_EXTENSIONS)
    retry: RetryConfig = field(default_factory=RetryConfig)
    presigned_expiry: int = _DEFAULT_PRESIGNED_EXPIRY


# --- Ana Sinif ---


class S3Uploader:
    """S3'e dosya/byte yukleme yoneticisi.

    aioboto3 ile asenkron upload, multipart, pre-signed URL,
    progress raporlama ve retry destegi saglar.

    Args:
        config: S3 upload konfigurasyonu.
        client: Opsiyonel onceden olusturulmus async S3 client (test icin).
    """

    def __init__(
        self,
        config: S3Config,
        client: AioS3Client | None = None,
    ) -> None:
        self._config = config
        self._client = client

    @property
    def config(self) -> S3Config:
        """Upload konfigurasyonunu dondurur."""
        return self._config

    async def _get_client(self) -> AioS3Client:
        """Async S3 client'i dondurur, yoksa olusturur.

        Returns:
            aioboto3 S3 client instance.

        Raises:
            S3UploadError: aioboto3 yuklenemedi veya client olusturulamadi.
        """
        if self._client is not None:
            return self._client

        try:
            import aioboto3  # type: ignore[import-untyped]
        except ImportError as exc:
            msg = "aioboto3 yuklu degil. 'pip install aioboto3' ile yukleyin."
            raise S3UploadError(msg) from exc

        try:
            session = aioboto3.Session()
            client: AioS3Client = await session.client(
                "s3",
                region_name=self._config.region,
            ).__aenter__()
            self._client = client
        except Exception as exc:
            msg = f"S3 client olusturulamadi: {exc}"
            raise S3UploadError(msg) from exc

        return self._client

    def validate_file(self, file_path: Path) -> tuple[int, str]:
        """Dosya tipi ve boyut dogrulamasi yapar.

        Args:
            file_path: Dogrulanacak dosya yolu.

        Returns:
            (dosya_boyutu, content_type) tuple.

        Raises:
            FileValidationError: Dosya bulunamadi, boyut veya tip hatasi.
        """
        if not file_path.exists():
            msg = f"Dosya bulunamadi: {file_path}"
            raise FileValidationError(msg)

        if not file_path.is_file():
            msg = f"Yol bir dosya degil: {file_path}"
            raise FileValidationError(msg)

        file_size = file_path.stat().st_size

        if file_size == 0:
            msg = f"Dosya bos: {file_path}"
            raise FileValidationError(msg)

        if file_size > self._config.max_file_size:
            max_mb = self._config.max_file_size / (1024 * 1024)
            actual_mb = file_size / (1024 * 1024)
            msg = f"Dosya boyutu siniri asildi: {actual_mb:.1f}MB (maks: {max_mb:.0f}MB)"
            raise FileValidationError(msg)

        ext = file_path.suffix.lower()
        if ext not in self._config.allowed_extensions:
            msg = (
                f"Dosya tipi desteklenmiyor: '{ext}'. "
                f"Izin verilen tipler: {sorted(self._config.allowed_extensions)}"
            )
            raise FileValidationError(msg)

        content_type = mimetypes.guess_type(str(file_path))[0] or _DEFAULT_CONTENT_TYPE
        return file_size, content_type

    def validate_bytes(
        self,
        data: bytes,
        content_type: str = _DEFAULT_CONTENT_TYPE,  # noqa: ARG002
    ) -> int:
        """Byte verisi dogrulamasi yapar.

        Args:
            data: Dogrulanacak byte verisi.
            content_type: MIME content type.

        Returns:
            Veri boyutu (byte).

        Raises:
            FileValidationError: Boyut hatasi.
        """
        size = len(data)

        if size == 0:
            msg = "Veri bos (0 byte)"
            raise FileValidationError(msg)

        if size > self._config.max_file_size:
            max_mb = self._config.max_file_size / (1024 * 1024)
            actual_mb = size / (1024 * 1024)
            msg = f"Veri boyutu siniri asildi: {actual_mb:.1f}MB (maks: {max_mb:.0f}MB)"
            raise FileValidationError(msg)

        return size

    async def _retry_operation(
        self,
        operation_name: str,
        operation: Callable[..., object],
        *args: object,
    ) -> object:
        """Bir islemi retry mekanizmasi ile calistirir.

        Args:
            operation_name: Islem adi (loglama icin).
            operation: Calistirilacak async fonksiyon.
            *args: Fonksiyona gonderilecek argumanlar.

        Returns:
            Islem sonucu.

        Raises:
            RetryExhaustedError: Tum retry denemeleri bitti.
        """
        last_error: Exception | None = None
        retry_cfg = self._config.retry
        delay = retry_cfg.initial_delay

        for attempt in range(1, retry_cfg.max_retries + 1):
            try:
                result = await operation(*args)  # type: ignore[misc]
                if attempt > 1:
                    await logger.ainfo(
                        "Retry basarili",
                        operation=operation_name,
                        attempt=attempt,
                    )
                return result
            except FileValidationError:
                raise
            except Exception as exc:
                last_error = exc
                await logger.awarning(
                    "Islem basarisiz, retry yapilacak",
                    operation=operation_name,
                    attempt=attempt,
                    max_retries=retry_cfg.max_retries,
                    delay=delay,
                    error=str(exc),
                )

                if attempt < retry_cfg.max_retries:
                    await asyncio.sleep(delay)
                    delay = min(delay * retry_cfg.backoff_factor, retry_cfg.max_delay)

        msg = f"{operation_name} {retry_cfg.max_retries} denemeden sonra basarisiz: {last_error}"
        raise RetryExhaustedError(msg) from last_error

    async def _single_upload(
        self,
        data: bytes,
        key: str,
        content_type: str,
        progress_callback: ProgressCallback | None = None,
    ) -> str:
        """Tek parca upload (put_object).

        Args:
            data: Yuklenecek byte verisi.
            key: S3 object key.
            content_type: MIME content type.
            progress_callback: Ilerleme callback fonksiyonu.

        Returns:
            S3 URL.

        Raises:
            S3UploadError: Upload basarisiz.
        """
        client = await self._get_client()
        total_size = len(data)

        if progress_callback:
            progress_callback(
                UploadProgress(
                    bytes_sent=0,
                    total_bytes=total_size,
                    percentage=0.0,
                    status=UploadStatus.IN_PROGRESS,
                ),
            )

        try:
            await client.put_object(
                Bucket=self._config.bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
            )
        except Exception as exc:
            if progress_callback:
                progress_callback(
                    UploadProgress(
                        bytes_sent=0,
                        total_bytes=total_size,
                        percentage=0.0,
                        status=UploadStatus.FAILED,
                    ),
                )
            msg = f"S3 upload basarisiz (key={key}): {exc}"
            raise S3UploadError(msg) from exc

        if progress_callback:
            progress_callback(
                UploadProgress(
                    bytes_sent=total_size,
                    total_bytes=total_size,
                    percentage=100.0,
                    status=UploadStatus.COMPLETED,
                ),
            )

        return f"https://{self._config.bucket}.s3.{self._config.region}.amazonaws.com/{key}"

    async def _multipart_upload(
        self,
        data: bytes,
        key: str,
        content_type: str,
        progress_callback: ProgressCallback | None = None,
    ) -> str:
        """Cok parcali upload (multipart upload API).

        Args:
            data: Yuklenecek byte verisi.
            key: S3 object key.
            content_type: MIME content type.
            progress_callback: Ilerleme callback fonksiyonu.

        Returns:
            S3 URL.

        Raises:
            S3UploadError: Multipart upload basarisiz.
        """
        client = await self._get_client()
        total_size = len(data)
        chunk_size = self._config.multipart_chunk_size
        total_parts = (total_size + chunk_size - 1) // chunk_size

        if progress_callback:
            progress_callback(
                UploadProgress(
                    bytes_sent=0,
                    total_bytes=total_size,
                    percentage=0.0,
                    status=UploadStatus.IN_PROGRESS,
                    part_number=0,
                    total_parts=total_parts,
                ),
            )

        upload_id: str | None = None

        try:
            # Multipart upload baslatma
            create_resp = await client.create_multipart_upload(
                Bucket=self._config.bucket,
                Key=key,
                ContentType=content_type,
            )
            upload_id = create_resp["UploadId"]

            parts: list[CompletedPartTypeDef] = []
            bytes_sent = 0

            for part_num in range(1, total_parts + 1):
                start = (part_num - 1) * chunk_size
                end = min(start + chunk_size, total_size)
                chunk = data[start:end]

                part_resp = await client.upload_part(
                    Bucket=self._config.bucket,
                    Key=key,
                    UploadId=upload_id,
                    PartNumber=part_num,
                    Body=chunk,
                )

                parts.append(
                    {
                        "ETag": part_resp["ETag"],
                        "PartNumber": part_num,
                    },
                )

                bytes_sent += len(chunk)
                percentage = (bytes_sent / total_size) * 100.0

                if progress_callback:
                    progress_callback(
                        UploadProgress(
                            bytes_sent=bytes_sent,
                            total_bytes=total_size,
                            percentage=percentage,
                            status=UploadStatus.IN_PROGRESS,
                            part_number=part_num,
                            total_parts=total_parts,
                        ),
                    )

                await logger.adebug(
                    "Multipart parca yuklendi",
                    key=key,
                    part=part_num,
                    total_parts=total_parts,
                    percentage=f"{percentage:.1f}%",
                )

            # Multipart upload tamamlama
            await client.complete_multipart_upload(
                Bucket=self._config.bucket,
                Key=key,
                UploadId=upload_id,
                MultipartUpload={"Parts": parts},
            )

            if progress_callback:
                progress_callback(
                    UploadProgress(
                        bytes_sent=total_size,
                        total_bytes=total_size,
                        percentage=100.0,
                        status=UploadStatus.COMPLETED,
                        part_number=total_parts,
                        total_parts=total_parts,
                    ),
                )

        except S3UploadError:
            raise
        except Exception as exc:
            # Multipart upload iptal etme
            if upload_id is not None:
                try:
                    await client.abort_multipart_upload(
                        Bucket=self._config.bucket,
                        Key=key,
                        UploadId=upload_id,
                    )
                except Exception:
                    await logger.aexception(
                        "Multipart upload iptal basarisiz",
                        key=key,
                        upload_id=upload_id,
                    )

            if progress_callback:
                progress_callback(
                    UploadProgress(
                        bytes_sent=0,
                        total_bytes=total_size,
                        percentage=0.0,
                        status=UploadStatus.FAILED,
                        part_number=0,
                        total_parts=total_parts,
                    ),
                )

            msg = f"Multipart upload basarisiz (key={key}): {exc}"
            raise S3UploadError(msg) from exc

        return f"https://{self._config.bucket}.s3.{self._config.region}.amazonaws.com/{key}"

    async def upload_bytes(
        self,
        data: bytes,
        key: str,
        content_type: str = _DEFAULT_CONTENT_TYPE,
        progress_callback: ProgressCallback | None = None,
    ) -> UploadResult:
        """Byte verisini S3'e asenkron olarak yukler.

        Veri boyutu multipart esigini asarsa otomatik olarak
        multipart upload kullanilir.

        Args:
            data: Yuklenecek byte verisi.
            key: S3 object key (dosya yolu).
            content_type: MIME content type.
            progress_callback: Ilerleme callback fonksiyonu.

        Returns:
            Upload sonuc bilgisi.

        Raises:
            FileValidationError: Veri dogrulama hatasi.
            RetryExhaustedError: Tum retry denemeleri bitti.
            S3UploadError: Upload basarisiz.
        """
        size = self.validate_bytes(data, content_type)
        use_multipart = size >= self._config.multipart_threshold

        await logger.ainfo(
            "Upload baslatiliyor",
            key=key,
            size_bytes=size,
            content_type=content_type,
            multipart=use_multipart,
        )

        upload_fn = self._multipart_upload if use_multipart else self._single_upload

        url = await self._retry_operation(
            f"upload({key})",
            upload_fn,
            data,
            key,
            content_type,
            progress_callback,
        )

        await logger.ainfo(
            "Upload tamamlandi",
            key=key,
            url=url,
            size_bytes=size,
            multipart=use_multipart,
        )

        return UploadResult(
            url=str(url),
            key=key,
            bucket=self._config.bucket,
            size_bytes=size,
            content_type=content_type,
            multipart=use_multipart,
        )

    async def upload_file(
        self,
        file_path: Path | str,
        key: str,
        progress_callback: ProgressCallback | None = None,
    ) -> UploadResult:
        """Dosyayi S3'e asenkron olarak yukler.

        Dosya boyutu multipart esigini asarsa otomatik olarak
        multipart upload kullanilir.

        Args:
            file_path: Yuklenecek dosya yolu.
            key: S3 object key.
            progress_callback: Ilerleme callback fonksiyonu.

        Returns:
            Upload sonuc bilgisi.

        Raises:
            FileValidationError: Dosya dogrulama hatasi.
            RetryExhaustedError: Tum retry denemeleri bitti.
            S3UploadError: Upload basarisiz.
        """
        path = Path(file_path)
        file_size, content_type = self.validate_file(path)

        await logger.ainfo(
            "Dosya upload baslatiliyor",
            file_path=str(path),
            key=key,
            size_bytes=file_size,
            content_type=content_type,
        )

        data = await asyncio.to_thread(path.read_bytes)
        return await self.upload_bytes(data, key, content_type, progress_callback)

    async def generate_presigned_url(
        self,
        key: str,
        expiry: int | None = None,
        http_method: str = "GET",
    ) -> str:
        """S3 object icin pre-signed URL olusturur.

        Args:
            key: S3 object key.
            expiry: URL gecerlilik suresi (saniye). None ise config'den alinir.
            http_method: HTTP method (GET veya PUT).

        Returns:
            Pre-signed URL string.

        Raises:
            S3UploadError: URL olusturma basarisiz.
        """
        client = await self._get_client()
        expiry_seconds = expiry if expiry is not None else self._config.presigned_expiry

        client_method = "get_object" if http_method == "GET" else "put_object"

        try:
            url: str = await client.generate_presigned_url(
                ClientMethod=client_method,
                Params={
                    "Bucket": self._config.bucket,
                    "Key": key,
                },
                ExpiresIn=expiry_seconds,
            )
        except Exception as exc:
            msg = f"Pre-signed URL olusturulamadi (key={key}): {exc}"
            raise S3UploadError(msg) from exc

        await logger.ainfo(
            "Pre-signed URL olusturuldu",
            key=key,
            http_method=http_method,
            expiry_seconds=expiry_seconds,
        )

        return url

    async def close(self) -> None:
        """S3 client'i kapatir."""
        if self._client is not None:
            try:
                await self._client.close()
            except Exception:
                await logger.aexception("S3 client kapatma hatasi")
            finally:
                self._client = None


def bytes_to_base64(data: bytes) -> str:
    """Byte verisini base64 string'e donusturur (fallback icin).

    Args:
        data: Donusturulecek byte verisi.

    Returns:
        Base64 encoded string.
    """
    return base64.b64encode(data).decode("utf-8")


def detect_content_type(file_path: str | Path) -> str:
    """Dosya uzantisindan content type belirler.

    Args:
        file_path: Dosya yolu.

    Returns:
        MIME content type.
    """
    content_type = mimetypes.guess_type(str(file_path))[0]
    return content_type or _DEFAULT_CONTENT_TYPE


def build_s3_key(
    prefix: str,
    filename: str,
    host_id: str | None = None,
) -> str:
    """S3 object key olusturur.

    Args:
        prefix: Key oneki (ornek: 'screenshots', 'logs').
        filename: Dosya adi.
        host_id: Host agent kimlik bilgisi.

    Returns:
        S3 object key (ornek: 'screenshots/macbook-pro/test.png').
    """
    parts = [prefix]
    if host_id:
        parts.append(host_id)
    parts.append(os.path.basename(filename))
    return "/".join(parts)
