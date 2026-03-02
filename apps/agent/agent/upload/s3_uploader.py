"""S3 upload yardimcisi - screenshot ve diger dosyalari S3'e yukler.

boto3 S3 client kullanarak dosya/byte upload islemleri gerceklestirir.
Diger runner'lar tarafindan da kullanilabilir (paylasilmis modul).
"""

from __future__ import annotations

import asyncio
import base64
from functools import partial
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from mypy_boto3_s3.client import S3Client

logger = structlog.get_logger()

# Varsayilan degerler
_DEFAULT_REGION: str = "eu-west-1"
_DEFAULT_CONTENT_TYPE: str = "image/png"


class S3UploadError(Exception):
    """S3 upload islemlerine ozel hata sinifi."""


class S3Uploader:
    """S3'e dosya/byte yukleme yardimcisi.

    Args:
        bucket: S3 bucket adi.
        region: AWS region (varsayilan: eu-west-1).
        client: Opsiyonel onceden olusturulmus S3 client (test icin).
    """

    def __init__(
        self,
        bucket: str,
        region: str = _DEFAULT_REGION,
        client: S3Client | None = None,
    ) -> None:
        self._bucket = bucket
        self._region = region
        self._client = client

    def _get_client(self) -> S3Client:
        """S3 client'i dondurur, yoksa olusturur.

        Returns:
            boto3 S3 client instance.

        Raises:
            S3UploadError: boto3 yuklenemedi veya client olusturulamadi.
        """
        if self._client is not None:
            return self._client

        try:
            import boto3
        except ImportError as exc:
            msg = "boto3 yuklu degil. 'pip install boto3' ile yukleyin."
            raise S3UploadError(msg) from exc

        try:
            client: S3Client = boto3.client("s3", region_name=self._region)
            self._client = client
        except Exception as exc:
            msg = f"S3 client olusturulamadi: {exc}"
            raise S3UploadError(msg) from exc

        return self._client

    def _upload_bytes_sync(
        self,
        data: bytes,
        key: str,
        content_type: str,
    ) -> str:
        """Senkron olarak byte verisi S3'e yukler.

        boto3 blocking oldugu icin bu fonksiyon
        asyncio.to_thread veya run_in_executor ile cagirilmalidir.

        Args:
            data: Yuklenecek byte verisi.
            key: S3 object key (dosya yolu).
            content_type: MIME content type.

        Returns:
            Yuklenen dosyanin S3 URL'i.

        Raises:
            S3UploadError: Upload basarisiz.
        """
        client = self._get_client()

        try:
            client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
            )
        except Exception as exc:
            msg = f"S3 upload basarisiz (key={key}): {exc}"
            raise S3UploadError(msg) from exc

        return f"https://{self._bucket}.s3.{self._region}.amazonaws.com/{key}"

    async def upload_bytes(
        self,
        data: bytes,
        key: str,
        content_type: str = _DEFAULT_CONTENT_TYPE,
    ) -> str:
        """Byte verisini S3'e asenkron olarak yukler.

        Args:
            data: Yuklenecek byte verisi.
            key: S3 object key (dosya yolu).
            content_type: MIME content type (varsayilan: image/png).

        Returns:
            Yuklenen dosyanin S3 URL'i.

        Raises:
            S3UploadError: Upload basarisiz.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            partial(self._upload_bytes_sync, data, key, content_type),
        )


def bytes_to_base64(data: bytes) -> str:
    """Byte verisini base64 string'e donusturur (fallback icin).

    Args:
        data: Donusturulecek byte verisi.

    Returns:
        Base64 encoded string.
    """
    return base64.b64encode(data).decode("utf-8")
