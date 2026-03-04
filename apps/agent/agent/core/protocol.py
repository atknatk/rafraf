"""WebSocket mesaj protokolu - serialize/deserialize islemleri.

shared/api-contracts/ws/agent-messages.json kontratina uyumlu.
"""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict


class ResourceMetrics(BaseModel):
    """Sistem kaynak metrikleri - frozen domain model."""

    model_config = ConfigDict(frozen=True)

    cpu_usage_percent: float
    memory_usage_percent: float
    disk_usage_percent: float
    disk_free_gb: float


class AlarmLevel(StrEnum):
    """Alarm seviyesi."""

    WARNING = "warning"
    CRITICAL = "critical"


class ResourceAlarm(BaseModel):
    """Kaynak kullanim alarmi - frozen domain model."""

    model_config = ConfigDict(frozen=True)

    source: str
    level: AlarmLevel
    current_value: float
    threshold: float
    message: str


class ResourceReportMessage(BaseModel):
    """Periyodik kaynak rapor mesaji (agent -> server)."""

    model_config = ConfigDict(frozen=True)

    type: str = "resource_report"
    host_id: str
    content: ResourceReportContent


class ResourceReportContent(BaseModel):
    """resource_report mesaj icerigi."""

    model_config = ConfigDict(frozen=True)

    host_id: str
    metrics: ResourceMetrics


class ResourceAlarmMessage(BaseModel):
    """Kaynak alarm mesaji (agent -> server)."""

    model_config = ConfigDict(frozen=True)

    type: str = "resource_alarm"
    host_id: str
    content: ResourceAlarmContent


class ResourceAlarmContent(BaseModel):
    """resource_alarm mesaj icerigi."""

    model_config = ConfigDict(frozen=True)

    host_id: str
    alarm: ResourceAlarm


class RegisterMessage(BaseModel):
    """Agent kayit mesaji (agent -> server)."""

    model_config = ConfigDict(frozen=True)

    type: str = "agent_register"
    host_id: str
    content: RegisterContent


class RegisterContent(BaseModel):
    """agent_register mesaj icerigi."""

    model_config = ConfigDict(frozen=True)

    host_id: str
    capabilities: list[str]
    os_info: str
    version: str


class RegisterAckPayload(BaseModel):
    """agent_register_ack mesaj icerigi (server -> agent)."""

    model_config = ConfigDict(frozen=True)

    host_id: str
    registered: bool
    server_time: str
    heartbeat_interval: int


class HeartbeatMessage(BaseModel):
    """Agent heartbeat mesaji (agent -> server)."""

    model_config = ConfigDict(frozen=True)

    type: str = "agent_heartbeat"
    host_id: str
    content: HeartbeatContent


class HeartbeatContent(BaseModel):
    """agent_heartbeat mesaj icerigi."""

    model_config = ConfigDict(frozen=True)

    host_id: str
    status: str
    uptime_seconds: int
    active_tasks: int
    resources: ResourceMetrics


def build_register_message(
    host_id: str,
    capabilities: list[str],
    os_info: str,
    version: str,
) -> str:
    """agent_register mesaji olusturur ve JSON string olarak dondurur."""
    content = RegisterContent(
        host_id=host_id,
        capabilities=capabilities,
        os_info=os_info,
        version=version,
    )
    message = RegisterMessage(
        host_id=host_id,
        content=content,
    )
    return message.model_dump_json()


def build_heartbeat_message(
    host_id: str,
    status: str,
    uptime_seconds: int,
    active_tasks: int,
    resources: ResourceMetrics,
) -> str:
    """agent_heartbeat mesaji olusturur ve JSON string olarak dondurur."""
    content = HeartbeatContent(
        host_id=host_id,
        status=status,
        uptime_seconds=uptime_seconds,
        active_tasks=active_tasks,
        resources=resources,
    )
    message = HeartbeatMessage(
        host_id=host_id,
        content=content,
    )
    return message.model_dump_json()


def parse_server_message(raw: str) -> dict[str, Any]:
    """Server'dan gelen mesaji parse eder.

    Returns:
        Parsed message dictionary with 'type' key.

    Raises:
        ValueError: Gecersiz JSON veya 'type' alani eksik.
    """
    try:
        data: dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError as exc:
        msg = f"Gecersiz JSON mesaji: {raw[:200]}"
        raise ValueError(msg) from exc

    if "type" not in data:
        msg = f"Mesajda 'type' alani eksik: {raw[:200]}"
        raise ValueError(msg)

    return data


def parse_register_ack(data: dict[str, Any]) -> RegisterAckPayload:
    """agent_register_ack mesajini parse eder.

    Raises:
        ValueError: Mesaj tipi uyumsuz veya content eksik.
    """
    if data.get("type") != "agent_register_ack":
        msg = f"Beklenen tip: agent_register_ack, gelen: {data.get('type')}"
        raise ValueError(msg)

    content = data.get("content")
    if content is None:
        msg = "agent_register_ack mesajinda 'content' alani eksik"
        raise ValueError(msg)

    return RegisterAckPayload(**content)


class ProjectSyncEntry(BaseModel):
    """Tek proje bilgisi (sync icin)."""

    model_config = ConfigDict(frozen=True)

    name: str
    repository_url: str | None = None
    local_path: str
    tech_stack: list[str] = []
    source: str


class ProjectSyncContent(BaseModel):
    """project_sync mesaj icerigi."""

    model_config = ConfigDict(frozen=True)

    host_id: str
    projects: list[ProjectSyncEntry]


class ProjectSyncMessage(BaseModel):
    """Proje sync mesaji (agent -> server)."""

    model_config = ConfigDict(frozen=True)

    type: str = "project_sync"
    host_id: str
    content: ProjectSyncContent


def build_project_sync_message(
    host_id: str,
    projects: list[ProjectSyncEntry],
) -> str:
    """project_sync mesaji olusturur ve JSON string olarak dondurur."""
    content = ProjectSyncContent(host_id=host_id, projects=projects)
    message = ProjectSyncMessage(host_id=host_id, content=content)
    return message.model_dump_json()


def build_resource_report_message(
    host_id: str,
    metrics: ResourceMetrics,
) -> str:
    """resource_report mesaji olusturur ve JSON string olarak dondurur."""
    content = ResourceReportContent(
        host_id=host_id,
        metrics=metrics,
    )
    message = ResourceReportMessage(
        host_id=host_id,
        content=content,
    )
    return message.model_dump_json()


def build_resource_alarm_message(
    host_id: str,
    alarm: ResourceAlarm,
) -> str:
    """resource_alarm mesaji olusturur ve JSON string olarak dondurur."""
    content = ResourceAlarmContent(
        host_id=host_id,
        alarm=alarm,
    )
    message = ResourceAlarmMessage(
        host_id=host_id,
        content=content,
    )
    return message.model_dump_json()
