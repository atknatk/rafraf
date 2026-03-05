"""Proje request/response Pydantic v2 schemas."""

import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ProjectStatus(StrEnum):
    """Proje durum degerleri."""

    ACTIVE = "active"
    PENDING = "pending"
    COMPLETED = "completed"
    ARCHIVED = "archived"


# ---------------------------------------------------------------------------
# Domain / entity model (frozen)
# ---------------------------------------------------------------------------


class ProjectEntity(BaseModel):
    """Proje domain modeli (immutable)."""

    model_config = ConfigDict(frozen=True)

    id: uuid.UUID = Field(..., description="Proje benzersiz ID")
    name: str = Field(..., description="Proje adi")
    description: str | None = Field(None, description="Proje aciklamasi")
    status: ProjectStatus = Field(..., description="Proje durumu")
    repository_url: str | None = Field(None, description="Git repository URL")
    tech_stack: list[str] = Field(default_factory=list, description="Kullanilan teknolojiler")
    last_activity_at: str | None = Field(None, description="Son aktivite zamani (ISO 8601)")
    last_activity_summary: str | None = Field(None, description="Son aktivite ozeti")
    source: str = Field(default="manual", description="Proje kaynagi: manual, agent_scan, agent_config")
    created_at: datetime = Field(..., description="Olusturulma zamani")
    updated_at: datetime = Field(..., description="Guncellenme zamani")


# ---------------------------------------------------------------------------
# REST request DTOs
# ---------------------------------------------------------------------------


class ProjectCreateRequest(BaseModel):
    """POST /api/v1/projects request."""

    name: str = Field(..., min_length=1, max_length=255, description="Proje adi")
    description: str | None = Field(None, description="Proje aciklamasi")
    status: ProjectStatus = Field(default=ProjectStatus.ACTIVE, description="Proje durumu")
    repository_url: str | None = Field(None, max_length=512, description="Git repository URL")
    local_path: str | None = Field(None, max_length=1024, description="Projenin lokal dizin yolu")
    tech_stack: list[str] = Field(default_factory=list, description="Kullanilan teknolojiler")
    source: str = Field(default="manual", description="Proje kaynagi: manual, agent_scan, agent_config")


class ProjectUpdateRequest(BaseModel, frozen=True):
    """PUT/PATCH /api/v1/projects/{project_id} request."""

    name: str | None = Field(None, min_length=1, max_length=255, description="Proje adi")
    description: str | None = Field(None, description="Proje aciklamasi")
    status: ProjectStatus | None = Field(None, description="Proje durumu")
    repository_url: str | None = Field(None, max_length=512, description="Git repository URL")
    local_path: str | None = Field(None, max_length=1024, description="Projenin lokal dizin yolu")
    tech_stack: list[str] | None = Field(None, description="Kullanilan teknolojiler")


class ProjectStatusUpdateRequest(BaseModel):
    """PATCH /api/v1/projects/{project_id}/status request."""

    status: ProjectStatus = Field(..., description="Yeni proje durumu")


class ProjectCreateResponse(BaseModel):
    """POST /api/v1/projects response."""

    id: uuid.UUID = Field(..., description="Proje benzersiz ID")
    name: str = Field(..., description="Proje adi")
    status: ProjectStatus = Field(..., description="Proje durumu")
    created_at: str = Field(..., description="Olusturulma zamani (ISO 8601)")


# ---------------------------------------------------------------------------
# REST response DTOs (not frozen)
# ---------------------------------------------------------------------------


class ProjectSummary(BaseModel):
    """Proje ozet bilgisi - liste gorunumu icin."""

    id: uuid.UUID = Field(..., description="Proje benzersiz ID")
    name: str = Field(..., description="Proje adi")
    status: ProjectStatus = Field(..., description="Proje durumu")
    local_path: str | None = Field(None, description="Projenin lokal dizin yolu")
    last_activity_at: str | None = Field(None, description="Son aktivite zamani")
    last_activity_summary: str | None = Field(None, description="Son aktivite ozeti")
    tech_stack: list[str] = Field(default_factory=list, description="Kullanilan teknolojiler")


class ProjectListResponse(BaseModel):
    """GET /api/v1/projects response."""

    projects: list[ProjectSummary] = Field(..., description="Proje listesi")
    total: int = Field(..., ge=0, description="Toplam proje sayisi")
    page: int = Field(..., ge=1, description="Mevcut sayfa numarasi")
    page_size: int = Field(..., ge=1, description="Sayfa basina proje sayisi")


class DeduplicateResponse(BaseModel):
    """POST /api/v1/projects/deduplicate response."""

    deleted_count: int = Field(..., ge=0, description="Silinen duplicate proje sayisi")


class ProjectDetailResponse(BaseModel):
    """GET /api/v1/projects/{project_id} response."""

    id: uuid.UUID = Field(..., description="Proje benzersiz ID")
    name: str = Field(..., description="Proje adi")
    description: str | None = Field(None, description="Proje aciklamasi")
    status: ProjectStatus = Field(..., description="Proje durumu")
    repository_url: str | None = Field(None, description="Git repository URL")
    local_path: str | None = Field(None, description="Projenin lokal dizin yolu")
    tech_stack: list[str] = Field(default_factory=list, description="Kullanilan teknolojiler")
    source: str = Field(default="manual", description="Proje kaynagi")
    last_activity_at: str | None = Field(None, description="Son aktivite zamani (ISO 8601)")
    last_activity_summary: str | None = Field(None, description="Son aktivite ozeti")
    created_at: str = Field(..., description="Olusturulma zamani (ISO 8601)")
    updated_at: str = Field(..., description="Guncellenme zamani (ISO 8601)")
