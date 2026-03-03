"""Dosya paylasimi request/response Pydantic v2 schemas."""

from pydantic import BaseModel, ConfigDict, Field

# Maximum file size: 50MB
_MAX_FILE_SIZE_BYTES = 52_428_800


class FileUploadURLRequest(BaseModel):
    """POST /api/v1/files/upload-url request body."""

    project_id: str = Field(..., description="Proje benzersiz ID (UUID)")
    file_name: str = Field(
        ..., min_length=1, max_length=255, description="Dosya adi (uzanti dahil)"
    )
    content_type: str = Field(
        ..., description="Dosya MIME tipi (ornek: application/pdf, image/png)"
    )
    file_size: int = Field(
        ...,
        gt=0,
        le=_MAX_FILE_SIZE_BYTES,
        description="Dosya boyutu bytes cinsinden (max 50MB)",
    )


class FileUploadURLResponse(BaseModel):
    """POST /api/v1/files/upload-url response body."""

    model_config = ConfigDict(frozen=True)

    upload_url: str = Field(
        ..., description="S3 pre-signed upload URL (PUT method ile kullanilir)"
    )
    file_key: str = Field(
        ..., description="S3 object key (indirme isteklerinde kullanilir)"
    )
    expiration_seconds: int = Field(
        ..., description="URL gecerlilik suresi saniye cinsinden"
    )


class FileDownloadURLRequest(BaseModel):
    """POST /api/v1/files/download-url request body."""

    project_id: str = Field(..., description="Proje benzersiz ID (UUID)")
    file_key: str = Field(
        ..., min_length=1, description="S3 object key (upload sonrasi donen key)"
    )


class FileDownloadURLResponse(BaseModel):
    """POST /api/v1/files/download-url response body."""

    model_config = ConfigDict(frozen=True)

    download_url: str = Field(
        ..., description="S3 pre-signed download URL (GET method ile kullanilir)"
    )
    file_key: str = Field(..., description="S3 object key")
    expiration_seconds: int = Field(
        ..., description="URL gecerlilik suresi saniye cinsinden"
    )
