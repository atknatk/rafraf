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
    created_at: datetime = Field(..., description="Olusturulma zamani")
    updated_at: datetime = Field(..., description="Guncellenme zamani")


# ---------------------------------------------------------------------------
# REST response DTOs (not frozen)
# ---------------------------------------------------------------------------


class ProjectSummary(BaseModel):
    """Proje ozet bilgisi - liste gorunumu icin."""

    id: uuid.UUID = Field(..., description="Proje benzersiz ID")
    name: str = Field(..., description="Proje adi")
    status: ProjectStatus = Field(..., description="Proje durumu")
    last_activity_at: str | None = Field(None, description="Son aktivite zamani")
    last_activity_summary: str | None = Field(None, description="Son aktivite ozeti")
    tech_stack: list[str] = Field(default_factory=list, description="Kullanilan teknolojiler")


class ProjectListResponse(BaseModel):
    """GET /api/v1/projects response."""

    projects: list[ProjectSummary] = Field(..., description="Proje listesi")
    total: int = Field(..., ge=0, description="Toplam proje sayisi")
    page: int = Field(..., ge=1, description="Mevcut sayfa numarasi")
    page_size: int = Field(..., ge=1, description="Sayfa basina proje sayisi")


class ProjectDetailResponse(BaseModel):
    """GET /api/v1/projects/{project_id} response."""

    id: uuid.UUID = Field(..., description="Proje benzersiz ID")
    name: str = Field(..., description="Proje adi")
    description: str | None = Field(None, description="Proje aciklamasi")
    status: ProjectStatus = Field(..., description="Proje durumu")
    repository_url: str | None = Field(None, description="Git repository URL")
    tech_stack: list[str] = Field(default_factory=list, description="Kullanilan teknolojiler")
    last_activity_at: str | None = Field(None, description="Son aktivite zamani (ISO 8601)")
    last_activity_summary: str | None = Field(None, description="Son aktivite ozeti")
    created_at: str = Field(..., description="Olusturulma zamani (ISO 8601)")
    updated_at: str = Field(..., description="Guncellenme zamani (ISO 8601)")
