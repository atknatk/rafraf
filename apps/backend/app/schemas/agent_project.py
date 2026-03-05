"""Agent-proje iliskisi ve Claude process Pydantic schemalar."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field


class AgentProjectSummary(BaseModel):
    """Tek proje ozeti — agent'in proje listesi icin."""

    model_config = ConfigDict(frozen=True)

    project_id: uuid.UUID
    project_name: str
    is_active: bool
    repository_url: str | None = None
    tech_stack: list[str] = Field(default_factory=list)


class AgentProjectsResponse(BaseModel):
    """GET /agents/{host_id}/projects yaniti."""

    agent_id: str
    projects: list[AgentProjectSummary]
    total: int


class AgentProjectUpdateRequest(BaseModel):
    """PATCH /agents/{host_id}/projects/{project_id} istegi."""

    is_active: bool


class ClaudeProcessInfo(BaseModel):
    """Calisan tek bir claude -p process bilgisi."""

    model_config = ConfigDict(frozen=True)

    pid: int
    cpu_percent: float = Field(ge=0)
    memory_mb: float = Field(ge=0)
    started_at: str | None = None
    cmdline: str | None = None


class AgentProcessesResponse(BaseModel):
    """GET /agents/{host_id}/processes yaniti."""

    agent_id: str
    processes: list[ClaudeProcessInfo]
    total: int
