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


class ClaudeProcessInfo(BaseModel):
    """Calisan tek bir claude process bilgisi."""

    model_config = ConfigDict(frozen=True)

    pid: int
    cpu_percent: float
    memory_mb: float
    started_at: str | None = None
    cmdline: str | None = None


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
    claude_processes: list[ClaudeProcessInfo] = []


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
    claude_processes: list[ClaudeProcessInfo] | None = None,
) -> str:
    """agent_heartbeat mesaji olusturur ve JSON string olarak dondurur."""
    content = HeartbeatContent(
        host_id=host_id,
        status=status,
        uptime_seconds=uptime_seconds,
        active_tasks=active_tasks,
        resources=resources,
        claude_processes=claude_processes or [],
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


# ------------------------------------------------------------------
# Task execution protocol (server -> agent -> server)
# ------------------------------------------------------------------


class TaskExecuteContent(BaseModel):
    """task_execute mesaj icerigi (server -> agent)."""

    model_config = ConfigDict(frozen=True)

    task_id: str
    runner: str
    action: str
    params: dict[str, Any] = {}


def parse_task_execute(data: dict[str, Any]) -> TaskExecuteContent:
    """task_execute mesajini parse eder.

    Raises:
        ValueError: content eksik veya gecersiz.
    """
    content = data.get("content")
    if content is None or not isinstance(content, dict):
        msg = "task_execute mesajinda 'content' alani eksik"
        raise ValueError(msg)

    return TaskExecuteContent(**content)


def build_task_result_message(
    *,
    task_id: str,
    host_id: str,
    success: bool,
    output: str | None = None,
    error: str | None = None,
    execution_time_ms: int = 0,
) -> str:
    """task_result mesaji olusturur ve JSON string olarak dondurur."""
    content: dict[str, Any] = {
        "task_id": task_id,
        "host_id": host_id,
        "success": success,
        "execution_time_ms": execution_time_ms,
    }
    if output is not None:
        content["output"] = output
    if error is not None:
        content["error"] = error

    message = {
        "type": "task_result",
        "content": content,
    }
    return json.dumps(message)


def build_task_error_message(
    *,
    task_id: str,
    host_id: str,
    error: str,
) -> str:
    """task_error mesaji olusturur ve JSON string olarak dondurur."""
    message = {
        "type": "task_error",
        "content": {
            "task_id": task_id,
            "host_id": host_id,
            "error": error,
        },
    }
    return json.dumps(message)


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


# ------------------------------------------------------------------
# Claude streaming protocol (server -> agent -> server)
# ------------------------------------------------------------------


class ClaudeTaskExecuteContent(BaseModel):
    """claude_task_execute mesaj icerigi (server -> agent)."""

    model_config = ConfigDict(frozen=True)

    task_id: str
    prompt: str
    project_dir: str | None = None
    session_id: str | None = None
    model: str = "sonnet"
    max_turns: int = 30
    append_system_prompt: str | None = None


def parse_claude_task_execute(data: dict[str, Any]) -> ClaudeTaskExecuteContent:
    """claude_task_execute mesajini parse eder.

    Raises:
        ValueError: content eksik veya gecersiz.
    """
    content = data.get("content")
    if content is None or not isinstance(content, dict):
        msg = "claude_task_execute mesajinda 'content' alani eksik"
        raise ValueError(msg)

    return ClaudeTaskExecuteContent(**content)


def build_claude_stream_delta_message(
    *,
    task_id: str,
    host_id: str,
    delta: str,
    index: int,
) -> str:
    """claude_stream_delta mesaji olusturur (agent -> server)."""
    message = {
        "type": "claude_stream_delta",
        "content": {
            "task_id": task_id,
            "host_id": host_id,
            "delta": delta,
            "index": index,
        },
    }
    return json.dumps(message)


def build_claude_stream_progress_message(
    *,
    task_id: str,
    host_id: str,
    phase: str,
    phase_label: str,
    current_tool: str | None,
    percentage: int,
    steps: list[dict[str, Any]],
) -> str:
    """claude_stream_progress mesaji olusturur (agent -> server)."""
    message = {
        "type": "claude_stream_progress",
        "content": {
            "task_id": task_id,
            "host_id": host_id,
            "phase": phase,
            "phase_label": phase_label,
            "current_tool": current_tool,
            "percentage": percentage,
            "steps": steps,
        },
    }
    return json.dumps(message)


def build_claude_stream_question_message(
    *,
    task_id: str,
    host_id: str,
    question_payload: dict[str, Any],
) -> str:
    """claude_stream_question mesaji olusturur (agent -> server)."""
    message = {
        "type": "claude_stream_question",
        "content": {
            "task_id": task_id,
            "host_id": host_id,
            "question_payload": question_payload,
        },
    }
    return json.dumps(message)


def build_claude_stream_end_message(
    *,
    task_id: str,
    host_id: str,
    session_id: str,
    full_text: str,
    model_used: str,
    tokens_input: int,
    tokens_output: int,
) -> str:
    """claude_stream_end mesaji olusturur (agent -> server)."""
    message = {
        "type": "claude_stream_end",
        "content": {
            "task_id": task_id,
            "host_id": host_id,
            "session_id": session_id,
            "full_text": full_text,
            "model_used": model_used,
            "tokens_input": tokens_input,
            "tokens_output": tokens_output,
        },
    }
    return json.dumps(message)


def build_claude_stream_error_message(
    *,
    task_id: str,
    host_id: str,
    error: str,
    returncode: int = -1,
) -> str:
    """claude_stream_error mesaji olusturur (agent -> server)."""
    message = {
        "type": "claude_stream_error",
        "content": {
            "task_id": task_id,
            "host_id": host_id,
            "error": error,
            "returncode": returncode,
        },
    }
    return json.dumps(message)
