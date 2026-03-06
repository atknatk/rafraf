"""Host Agent registry and health monitoring schemas (Pydantic v2)."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class AgentStatus(StrEnum):
    """Possible states of a host agent."""

    ONLINE = "online"
    OFFLINE = "offline"
    BUSY = "busy"


class AgentCapability(StrEnum):
    """Supported agent capabilities / runners."""

    DOCKER = "docker"
    PLAYWRIGHT = "playwright"
    MAESTRO_IOS = "maestro_ios"
    MAESTRO_ANDROID = "maestro_android"
    SHELL = "shell"
    XCODE_BUILD = "xcode_build"
    ANDROID_BUILD = "android_build"
    GIT = "git"
    PYTHON = "python"
    NODEJS = "nodejs"


# ---------------------------------------------------------------------------
# WebSocket message payloads (frozen domain models)
# ---------------------------------------------------------------------------


class ResourceInfo(BaseModel):
    """System resource usage snapshot."""

    model_config = ConfigDict(frozen=True)

    cpu_usage_percent: float = Field(..., ge=0, le=100, description="CPU kullanim yuzdesi")
    memory_usage_percent: float = Field(..., ge=0, le=100, description="RAM kullanim yuzdesi")
    disk_usage_percent: float = Field(..., ge=0, le=100, description="Disk kullanim yuzdesi")
    disk_free_gb: float = Field(..., ge=0, description="Bos disk alani (GB)")


class AgentRegisterPayload(BaseModel):
    """Payload sent by an agent to register itself."""

    model_config = ConfigDict(frozen=True)

    host_id: str = Field(..., min_length=1, max_length=100, description="Benzersiz host kimlik")
    capabilities: list[AgentCapability] = Field(..., description="Desteklenen yetenekler")
    os_info: str = Field(..., description="Isletim sistemi bilgisi")
    version: str = Field(..., description="Agent yazilim surumu")


class ClaudeProcessInfo(BaseModel):
    """Calisan tek bir claude process bilgisi."""

    model_config = ConfigDict(frozen=True)

    pid: int = Field(..., description="Process ID")
    cpu_percent: float = Field(..., ge=0, description="CPU kullanim yuzdesi")
    memory_mb: float = Field(..., ge=0, description="RAM kullanimi (MB)")
    started_at: str | None = Field(None, description="Baslangic zamani (ISO 8601)")
    cmdline: str | None = Field(None, description="Komut satiri ozeti")


class AgentHeartbeatPayload(BaseModel):
    """Payload sent by an agent as a periodic health report."""

    model_config = ConfigDict(frozen=True)

    host_id: str = Field(..., description="Host kimlik bilgisi")
    status: AgentStatus = Field(..., description="Agent durumu")
    uptime_seconds: int = Field(..., ge=0, description="Agent calisma suresi (saniye)")
    active_tasks: int = Field(..., ge=0, description="Aktif gorev sayisi")
    resources: ResourceInfo = Field(..., description="Sistem kaynak bilgileri")
    claude_processes: list[ClaudeProcessInfo] = Field(
        default_factory=list,
        description="Calisan claude process listesi",
    )


class AgentRegisterAckPayload(BaseModel):
    """Acknowledgement sent back to the agent after registration."""

    model_config = ConfigDict(frozen=True)

    host_id: str = Field(..., description="Onaylanan host kimlik bilgisi")
    registered: bool = Field(..., description="Kayit basarili mi?")
    server_time: str = Field(..., description="Sunucu zamani (ISO 8601)")
    heartbeat_interval: int = Field(..., description="Heartbeat gonderme araligi (saniye)")


# ---------------------------------------------------------------------------
# Task management schemas
# ---------------------------------------------------------------------------


class TaskStatus(StrEnum):
    """Agent task lifecycle states."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


class AgentTaskSummary(BaseModel):
    """Summary of a single agent task."""

    task_id: str
    host_id: str
    runner: str
    action: str
    status: TaskStatus
    project_id: str | None = None
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None
    duration_ms: int | None = None
    error: str | None = None


class AgentTaskListResponse(BaseModel):
    """Response for GET /api/v1/agents/{host_id}/tasks."""

    tasks: list[AgentTaskSummary]
    total: int
    pending_count: int


class DispatchTaskRequest(BaseModel):
    """Request body for POST /api/v1/agents/{host_id}/tasks."""

    runner: str = Field(..., description="Runner tipi: shell, docker, playwright, maestro")
    action: str = Field(..., description="Runner aksiyonu")
    params: dict[str, object] = Field(default_factory=dict)
    project_id: str | None = None


# ---------------------------------------------------------------------------
# REST response schemas (not frozen — these are DTOs)
# ---------------------------------------------------------------------------


class AgentSummary(BaseModel):
    """Summary representation of a single agent for list responses."""

    host_id: str
    status: AgentStatus
    capabilities: list[AgentCapability]
    last_heartbeat_at: str | None = None
    os_info: str | None = None
    uptime_seconds: int | None = None
    active_tasks: int | None = None
    resources: ResourceInfo | None = None


class AgentListResponse(BaseModel):
    """Response for GET /api/v1/agents."""

    agents: list[AgentSummary]
    total: int
    online_count: int


class AgentDetailResponse(BaseModel):
    """Response for GET /api/v1/agents/{host_id}."""

    host_id: str
    status: AgentStatus
    capabilities: list[AgentCapability]
    last_heartbeat_at: str | None = None
    registered_at: str
    os_info: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
    uptime_seconds: int | None = None
    active_tasks: int | None = None
    resources: ResourceInfo | None = None
    claude_processes: list[ClaudeProcessInfo] = Field(default_factory=list)
    dangerously_skip_permissions: bool = False


class AgentSettingsRequest(BaseModel):
    """Request body for PATCH /api/v1/agents/{host_id}/settings."""

    dangerously_skip_permissions: bool
