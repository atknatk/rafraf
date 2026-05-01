"""Kesfedilen proje veri modelleri."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class DiscoveredProject(BaseModel):
    """Agent tarafindan kesfedilen proje (frozen domain model)."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(..., description="Proje adi")
    repository_url: str | None = Field(None, description="Git remote URL")
    local_path: str = Field(..., description="Yerel dizin yolu")
    tech_stack: list[str] = Field(default_factory=list, description="Teknoloji tespiti")
    source: str = Field(..., description="Kaynak: agent_config veya agent_scan")
