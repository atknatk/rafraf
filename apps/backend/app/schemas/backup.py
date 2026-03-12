"""Pydantic schemas for backup/disaster recovery endpoints."""

from pydantic import BaseModel, Field


class BackupResponse(BaseModel):
    """Response after creating a backup."""

    status: str = Field(description="Backup durumu (success/failed)")
    backup_type: str = Field(description="Backup tipi (postgres/redis)")
    s3_key: str = Field(description="S3 object key")
    size_bytes: str = Field(description="Backup boyutu (bytes)")
    timestamp: str = Field(description="Backup zamani (ISO 8601)")
    duration_seconds: str = Field(description="Backup suresi (saniye)")
    database: str = Field(default="", description="Veritabani adi (postgres icin)")


class BackupListItem(BaseModel):
    """Single backup entry in the list."""

    key: str = Field(description="S3 object key")
    backup_type: str = Field(description="Backup tipi (postgres/redis)")
    size_bytes: str = Field(description="Dosya boyutu (bytes)")
    last_modified: str = Field(description="Son degisiklik zamani")


class BackupListResponse(BaseModel):
    """Response for listing backups."""

    backups: list[BackupListItem] = Field(description="Backup listesi")
    total: int = Field(description="Toplam backup sayisi")


class BackupRotationResponse(BaseModel):
    """Response after rotating old backups."""

    postgres_deleted: int = Field(description="Silinen PostgreSQL backup sayisi")
    redis_deleted: int = Field(description="Silinen Redis backup sayisi")
    retention_days: int = Field(description="Saklama suresi (gun)")


class BackupVerifyRequest(BaseModel):
    """Request to verify a backup."""

    s3_key: str = Field(description="Dogrulanacak backup'in S3 key'i")


class BackupVerifyResponse(BaseModel):
    """Response after verifying a backup."""

    status: str = Field(description="Dogrulama durumu (verified/failed)")
    s3_key: str = Field(description="S3 object key")
    compressed_size_bytes: str = Field(default="", description="Sikistirilmis boyut")
    decompressed_size_bytes: str = Field(default="", description="Acilmis boyut")
    error: str = Field(default="", description="Hata mesaji (basarisizsa)")


class BackupStatusResponse(BaseModel):
    """Overall backup status response."""

    health: str = Field(description="Genel durum (healthy/warning/critical)")
    retention_days: str = Field(description="Saklama suresi (gun)")
    issues: str = Field(description="Bilinen sorunlar")
    latest_postgres: dict[str, str] = Field(description="Son PostgreSQL backup")
    latest_redis: dict[str, str] = Field(description="Son Redis backup")
    recent_backups: list[dict[str, str]] = Field(description="Son backup'lar")
