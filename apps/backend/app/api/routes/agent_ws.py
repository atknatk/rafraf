"""WebSocket endpoint for Host Agent connections.

Agents authenticate with an API key, register their capabilities,
and send periodic heartbeat messages.
"""

from datetime import UTC, datetime
from uuid import uuid4

import structlog
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.config import get_settings
from app.core.websocket import ConnectionManager
from app.schemas.agent import (
    AgentHeartbeatPayload,
    AgentRegisterAckPayload,
    AgentRegisterPayload,
)
from app.core.database import async_session_factory
from app.services.agent_registry_service import agent_registry
from app.services.project_service import ProjectService
from app.services.task_manager_service import TaskManager

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

router = APIRouter()

# Dedicated connection manager for agent connections (separate from iOS clients)
agent_manager = ConnectionManager(heartbeat_interval=30, heartbeat_timeout=10)

# Task manager singleton (initialized lazily to avoid circular imports)
_task_manager: TaskManager | None = None


def get_task_manager() -> TaskManager:
    """Get or create the global task manager."""
    global _task_manager  # noqa: PLW0603
    if _task_manager is None:
        _task_manager = TaskManager(
            agent_registry=agent_registry,
            agent_manager=agent_manager,
        )
    return _task_manager


def _build_agent_message(
    msg_type: str,
    content: dict[str, object],
) -> dict[str, object]:
    """Build a server-to-agent WebSocket message dict."""
    return {
        "id": str(uuid4()),
        "type": msg_type,
        "content": content,
        "metadata": {
            "timestamp": datetime.now(tz=UTC).isoformat(),
            "direction": "server_to_agent",
        },
    }


@router.websocket("/ws/agent")
async def agent_websocket_endpoint(
    websocket: WebSocket,
    api_key: str = Query(..., alias="api_key"),
) -> None:
    """Handle Host Agent WebSocket connections.

    Authenticates via API key query parameter, waits for agent_register,
    then processes heartbeat messages.
    """
    settings = get_settings()

    # --- API key authentication ---
    if api_key != settings.agent_api_key:
        await logger.awarning("agent_ws_auth_failed", reason="invalid_api_key")
        await websocket.close(code=4008, reason="Invalid API key")
        return

    # --- Connection setup (use a placeholder user_id / session_id) ---
    connection_id = await agent_manager.connect(
        websocket=websocket,
        user_id="agent",
        session_id=str(uuid4()),
    )

    await logger.ainfo("agent_ws_connected", connection_id=connection_id)

    registered_host_id: str | None = None

    try:
        while True:
            raw_data: dict[str, object] = await websocket.receive_json()
            msg_type = raw_data.get("type")

            if msg_type == "agent_register":
                registered_host_id = await _handle_register(
                    raw_data, connection_id, settings.ws_heartbeat_interval
                )
            elif msg_type == "agent_heartbeat":
                await _handle_heartbeat(raw_data, connection_id)
            elif msg_type == "project_sync":
                await _handle_project_sync(raw_data, connection_id)
            elif msg_type == "resource_report":
                await _handle_resource_report(raw_data, connection_id)
            elif msg_type == "resource_alarm":
                await _handle_resource_alarm(raw_data, connection_id)
            elif msg_type == "task_result":
                await _handle_task_result(raw_data, connection_id)
            elif msg_type == "task_error":
                await _handle_task_error(raw_data, connection_id)
            elif msg_type == "pong":
                await logger.adebug(
                    "agent_pong_received",
                    connection_id=connection_id,
                )
            elif msg_type == "ping":
                pong_msg = _build_agent_message("pong", {
                    "timestamp": datetime.now(tz=UTC).isoformat(),
                })
                await agent_manager.send_json(connection_id, pong_msg)
            else:
                await logger.awarning(
                    "agent_ws_unknown_message",
                    connection_id=connection_id,
                    message_type=msg_type,
                )
    except WebSocketDisconnect:
        await logger.ainfo(
            "agent_ws_client_disconnected",
            connection_id=connection_id,
            host_id=registered_host_id,
        )
    except Exception:
        await logger.aexception(
            "agent_ws_unexpected_error",
            connection_id=connection_id,
        )
    finally:
        if registered_host_id is not None:
            await agent_registry.mark_disconnected(registered_host_id)
        else:
            await agent_registry.unregister_by_connection(connection_id)
        await agent_manager.disconnect(connection_id)


async def _handle_register(
    raw_data: dict[str, object],
    connection_id: str,
    heartbeat_interval: int,
) -> str:
    """Process an agent_register message and return the host_id."""
    content = raw_data.get("content", {})
    if not isinstance(content, dict):
        content = {}

    payload = AgentRegisterPayload(
        host_id=str(content.get("host_id", "")),
        capabilities=content.get("capabilities", []),
        os_info=str(content.get("os_info", "")),
        version=str(content.get("version", "")),
    )

    await agent_registry.register_agent(payload, connection_id)

    ack = AgentRegisterAckPayload(
        host_id=payload.host_id,
        registered=True,
        server_time=datetime.now(tz=UTC).isoformat(),
        heartbeat_interval=heartbeat_interval,
    )

    ack_msg = _build_agent_message(
        "agent_register_ack",
        ack.model_dump(),
    )
    await agent_manager.send_json(connection_id, ack_msg)

    await logger.ainfo(
        "agent_registered_via_ws",
        host_id=payload.host_id,
        connection_id=connection_id,
    )
    return payload.host_id


async def _handle_heartbeat(
    raw_data: dict[str, object],
    connection_id: str,
) -> None:
    """Process an agent_heartbeat message."""
    content = raw_data.get("content", {})
    if not isinstance(content, dict):
        content = {}

    resources_raw = content.get("resources", {})
    if not isinstance(resources_raw, dict):
        resources_raw = {}

    payload = AgentHeartbeatPayload(
        host_id=str(content.get("host_id", "")),
        status=content.get("status", "online"),
        uptime_seconds=int(content.get("uptime_seconds", 0)),
        active_tasks=int(content.get("active_tasks", 0)),
        resources={
            "cpu_usage_percent": float(resources_raw.get("cpu_usage_percent", 0)),
            "memory_usage_percent": float(resources_raw.get("memory_usage_percent", 0)),
            "disk_usage_percent": float(resources_raw.get("disk_usage_percent", 0)),
            "disk_free_gb": float(resources_raw.get("disk_free_gb", 0)),
        },
    )

    found = await agent_registry.process_heartbeat(payload)
    if not found:
        await logger.awarning(
            "agent_heartbeat_unknown",
            host_id=payload.host_id,
            connection_id=connection_id,
        )


async def _handle_project_sync(
    raw_data: dict[str, object],
    connection_id: str,
) -> None:
    """Process a project_sync message from the agent."""
    content = raw_data.get("content", {})
    if not isinstance(content, dict):
        content = {}

    projects_data = content.get("projects", [])
    if not isinstance(projects_data, list):
        projects_data = []

    synced_count = 0
    async with async_session_factory() as session:
        service = ProjectService(session)
        for proj in projects_data:
            if not isinstance(proj, dict):
                continue
            name = str(proj.get("name", ""))
            if not name:
                continue
            await service.upsert_from_agent(
                name=name,
                repository_url=proj.get("repository_url"),
                tech_stack=proj.get("tech_stack", []),
                source=str(proj.get("source", "agent_scan")),
            )
            synced_count += 1
        await session.commit()

    ack = _build_agent_message("project_sync_ack", {
        "synced_count": synced_count,
        "status": "ok",
    })
    await agent_manager.send_json(connection_id, ack)

    await logger.ainfo(
        "project_sync_completed",
        connection_id=connection_id,
        count=synced_count,
    )


async def _handle_resource_report(
    raw_data: dict[str, object],
    connection_id: str,
) -> None:
    """Process a resource_report message — update agent registry metrics."""
    content = raw_data.get("content", {})
    if not isinstance(content, dict):
        content = {}

    host_id = str(content.get("host_id", ""))
    metrics_raw = content.get("metrics", {})
    if not isinstance(metrics_raw, dict):
        metrics_raw = {}

    resources = {
        "cpu_usage_percent": float(metrics_raw.get("cpu_usage_percent", 0)),
        "memory_usage_percent": float(metrics_raw.get("memory_usage_percent", 0)),
        "disk_usage_percent": float(metrics_raw.get("disk_usage_percent", 0)),
        "disk_free_gb": float(metrics_raw.get("disk_free_gb", 0)),
    }

    found = await agent_registry.update_resources(host_id, resources)
    if found:
        await logger.adebug(
            "agent_resource_report_processed",
            host_id=host_id,
            connection_id=connection_id,
        )
    else:
        await logger.awarning(
            "agent_resource_report_unknown_host",
            host_id=host_id,
            connection_id=connection_id,
        )


async def _handle_resource_alarm(
    raw_data: dict[str, object],
    connection_id: str,
) -> None:
    """Process a resource_alarm message — log the alarm."""
    content = raw_data.get("content", {})
    if not isinstance(content, dict):
        content = {}

    host_id = str(content.get("host_id", ""))
    alarm_raw = content.get("alarm", {})
    if not isinstance(alarm_raw, dict):
        alarm_raw = {}

    await logger.awarning(
        "agent_resource_alarm",
        host_id=host_id,
        connection_id=connection_id,
        source=alarm_raw.get("source"),
        level=alarm_raw.get("level"),
        current_value=alarm_raw.get("current_value"),
        threshold=alarm_raw.get("threshold"),
        message=alarm_raw.get("message"),
    )


async def _handle_task_result(
    raw_data: dict[str, object],
    connection_id: str,
) -> None:
    """Process a task_result message — resolve the pending future."""
    content = raw_data.get("content", {})
    if not isinstance(content, dict):
        content = {}

    task_id = str(content.get("task_id", ""))
    if not task_id:
        await logger.awarning("task_result_missing_task_id", connection_id=connection_id)
        return

    tm = get_task_manager()
    found = tm.complete(task_id, dict(content))

    await logger.ainfo(
        "task_result_received",
        task_id=task_id,
        connection_id=connection_id,
        resolved=found,
        success=content.get("success"),
    )


async def _handle_task_error(
    raw_data: dict[str, object],
    connection_id: str,
) -> None:
    """Process a task_error message — reject the pending future."""
    content = raw_data.get("content", {})
    if not isinstance(content, dict):
        content = {}

    task_id = str(content.get("task_id", ""))
    error_msg = str(content.get("error", "Bilinmeyen hata"))

    if not task_id:
        await logger.awarning("task_error_missing_task_id", connection_id=connection_id)
        return

    tm = get_task_manager()
    found = tm.fail(task_id, error_msg)

    await logger.awarning(
        "task_error_received",
        task_id=task_id,
        connection_id=connection_id,
        resolved=found,
        error=error_msg,
    )
