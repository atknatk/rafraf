"""WebSocket endpoint for Host Agent connections.

Agents authenticate with an API key, register their capabilities,
and send periodic heartbeat messages.
"""

import uuid
from datetime import UTC, datetime
from uuid import uuid4

import structlog
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.config import get_settings
from app.core.database import async_session_factory
from app.core.websocket import ConnectionManager
from app.schemas.agent import (
    AgentHeartbeatPayload,
    AgentRegisterAckPayload,
    AgentRegisterPayload,
    ClaudeProcessInfo,
)
from app.services.agent_project_service import AgentProjectService
from app.services.bridge_registry_service import bridge_registry
from app.services.claude_stream_manager import ClaudeStreamManager
from app.services.project_service import ProjectService
from app.services.task_manager_service import TaskManager

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

router = APIRouter()

# Dedicated connection manager for agent connections (separate from iOS clients)
# NOTE: ``kind="raw_bridge_ws"`` keeps the iOS ↔ bridge gauge separation
# clear *and* avoids double-counting with the canonical
# ``ws_connections_active{kind="bridge"}`` gauge that
# ``BridgeRegistryService`` increments on bridge *registration* (not raw
# socket accept). The metric we care about for capacity planning is
# "registered + healthy bridges", so we keep that one in the registry
# service and label this lower-level WS gauge separately for diagnostics.
agent_manager = ConnectionManager(
    heartbeat_interval=30,
    heartbeat_timeout=10,
    kind="raw_bridge_ws",
)

# Wire the bridge-side ConnectionManager into the registry singleton so
# ClaudeCodeRunner can route ``command.claude.run`` envelopes (T1.1).
bridge_registry.set_agent_manager(agent_manager)

# Task manager singleton (initialized lazily to avoid circular imports)
_task_manager: TaskManager | None = None


def get_task_manager() -> TaskManager:
    """Get or create the global task manager."""
    global _task_manager  # noqa: PLW0603
    if _task_manager is None:
        _task_manager = TaskManager(
            agent_registry=bridge_registry,
            agent_manager=agent_manager,
        )
    return _task_manager


# Claude stream manager singleton
_claude_stream_manager: ClaudeStreamManager | None = None


def get_claude_stream_manager() -> ClaudeStreamManager:
    """Get or create the global claude stream manager.

    Imports the iOS-side ConnectionManager singleton lazily so the
    ``forward_*`` methods (T1.2 Agent Teams) can push to iOS sessions
    without requiring the import at module load time (which would create
    a cycle through ``websocket.py``).
    """
    global _claude_stream_manager  # noqa: PLW0603
    if _claude_stream_manager is None:
        # Lazy import to avoid a cycle through websocket.py at startup.
        from app.api.routes.websocket import manager as ios_manager  # noqa: PLC0415

        _claude_stream_manager = ClaudeStreamManager(
            agent_registry=bridge_registry,
            agent_manager=agent_manager,
            ios_manager=ios_manager,
        )
    return _claude_stream_manager


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
    # TODO(T1.x bridge pairing): replace agent_api_key shared-secret auth with
    # the per-bridge ``pairing_token`` lookup (see ``bridges.pairing_token``
    # column added in alembic 014). The ``agent_api_key`` setting is
    # deprecated but kept as the only auth mechanism until T1.x lands.
    if api_key != settings.agent_api_key:
        await logger.awarning("agent_ws_auth_failed", reason="invalid_api_key")
        await websocket.close(code=4008, reason="Invalid API key")
        return
    await logger.awarning(
        "agent_api_key_auth_deprecated",
        message=(
            "agent_api_key shared-secret auth is deprecated; bridge "
            "pairing_token mechanism lands in T1.x"
        ),
    )

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
            elif msg_type == "claude_stream_delta":
                await _handle_claude_stream_delta(raw_data, connection_id)
            elif msg_type == "claude_stream_progress":
                await _handle_claude_stream_progress(raw_data, connection_id)
            elif msg_type == "claude_stream_question":
                await _handle_claude_stream_question(raw_data, connection_id)
            elif msg_type == "claude_stream_end":
                await _handle_claude_stream_end(raw_data, connection_id)
            elif msg_type == "claude_stream_error":
                await _handle_claude_stream_error(raw_data, connection_id)
            elif msg_type == "event.usage.report":
                # Statusline-driven, broadcast event (no RPC correlation).
                # Forwarded to every connected iOS session as a typed
                # ``usage.report`` message (T1.2). MUST be matched before
                # the generic ``event.*`` branch because dispatch_event
                # drops correlation-less envelopes.
                await _handle_usage_report(raw_data)
            elif msg_type == "event.session.title":
                # Storage-watcher-driven, broadcast event (no RPC
                # correlation). Resolves session→user via SessionRepository
                # and forwards a typed ``session.title`` message to that
                # owner's iOS connections (T1.2-fix H-1). MUST be matched
                # before the generic ``event.*`` branch.
                await _handle_session_title(raw_data)
            elif msg_type == "event.session.pr_opened":
                # Storage-watcher-driven, broadcast event (no RPC
                # correlation). Resolves session→user via SessionRepository
                # and forwards a typed ``session.pr_opened`` message
                # (T1.2-fix H-1). MUST be matched before the generic
                # ``event.*`` branch.
                await _handle_session_pr_opened(raw_data)
            elif isinstance(msg_type, str) and msg_type.startswith("event."):
                # Bridge → backend RPC events (T1.1). Routed to the
                # ClaudeCodeRunner subscriber that owns the matching
                # correlation_id.
                await bridge_registry.dispatch_event(raw_data)
            elif msg_type == "pong":
                await logger.adebug(
                    "agent_pong_received",
                    connection_id=connection_id,
                )
            elif msg_type == "ping":
                pong_msg = _build_agent_message(
                    "pong",
                    {
                        "timestamp": datetime.now(tz=UTC).isoformat(),
                    },
                )
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
            await bridge_registry.mark_disconnected(registered_host_id)
        else:
            await bridge_registry.unregister_by_connection(connection_id)
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

    await bridge_registry.register_agent(payload, connection_id)

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

    # Claude process listesini parse et
    processes_raw = content.get("claude_processes", [])
    if not isinstance(processes_raw, list):
        processes_raw = []
    claude_processes = [
        ClaudeProcessInfo(
            pid=int(p.get("pid", 0)),
            cpu_percent=float(p.get("cpu_percent", 0)),
            memory_mb=float(p.get("memory_mb", 0)),
            started_at=p.get("started_at"),
            cmdline=p.get("cmdline"),
        )
        for p in processes_raw
        if isinstance(p, dict) and p.get("pid")
    ]

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
        claude_processes=claude_processes,
    )

    found = await bridge_registry.process_heartbeat(payload)
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

    host_id = str(content.get("host_id", ""))
    synced_count = 0
    archived_count = 0
    async with async_session_factory() as session:
        project_svc = ProjectService(session)
        agent_project_svc = AgentProjectService(session)
        synced_project_ids: set[uuid.UUID] = set()
        for proj in projects_data:
            if not isinstance(proj, dict):
                continue
            name = str(proj.get("name", ""))
            if not name:
                continue
            result = await project_svc.upsert_from_agent(
                name=name,
                repository_url=proj.get("repository_url"),
                local_path=proj.get("local_path"),
                tech_stack=proj.get("tech_stack", []),
                source=str(proj.get("source", "agent_scan")),
            )
            synced_project_ids.add(result.id)
            if host_id:
                await agent_project_svc.link_project_to_agent(host_id, result.id)
            synced_count += 1

        # Artik scan'de bulunmayan agent_scan projelerini archive et
        if host_id:
            archived_count = await agent_project_svc.sync_and_archive_removed(
                host_id, synced_project_ids
            )

        await session.commit()

    ack = _build_agent_message(
        "project_sync_ack",
        {
            "synced_count": synced_count,
            "archived_count": archived_count,
            "status": "ok",
        },
    )
    await agent_manager.send_json(connection_id, ack)

    await logger.ainfo(
        "project_sync_completed",
        connection_id=connection_id,
        synced=synced_count,
        archived=archived_count,
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

    found = await bridge_registry.update_resources(host_id, resources)
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


# ------------------------------------------------------------------
# Claude streaming handlers
# ------------------------------------------------------------------


async def _handle_claude_stream_delta(
    raw_data: dict[str, object],
    _connection_id: str,
) -> None:
    """Forward claude_stream_delta to ClaudeStreamManager."""
    content = raw_data.get("content", {})
    if not isinstance(content, dict):
        return

    task_id = str(content.get("task_id", ""))
    if not task_id:
        return

    csm = get_claude_stream_manager()
    await csm.handle_stream_delta(
        task_id=task_id,
        delta=str(content.get("delta", "")),
        index=int(content.get("index", 0)),
    )


async def _handle_claude_stream_progress(
    raw_data: dict[str, object],
    _connection_id: str,
) -> None:
    """Forward claude_stream_progress to ClaudeStreamManager."""
    content = raw_data.get("content", {})
    if not isinstance(content, dict):
        return

    task_id = str(content.get("task_id", ""))
    if not task_id:
        return

    csm = get_claude_stream_manager()
    await csm.handle_stream_progress(task_id=task_id, progress_data=dict(content))


async def _handle_claude_stream_question(
    raw_data: dict[str, object],
    _connection_id: str,
) -> None:
    """Forward claude_stream_question to ClaudeStreamManager."""
    content = raw_data.get("content", {})
    if not isinstance(content, dict):
        return

    task_id = str(content.get("task_id", ""))
    if not task_id:
        return

    question_payload = content.get("question_payload", {})
    if not isinstance(question_payload, dict):
        question_payload = {}

    csm = get_claude_stream_manager()
    await csm.handle_stream_question(task_id=task_id, question_data=question_payload)


async def _handle_claude_stream_end(
    raw_data: dict[str, object],
    _connection_id: str,
) -> None:
    """Forward claude_stream_end to ClaudeStreamManager."""
    content = raw_data.get("content", {})
    if not isinstance(content, dict):
        return

    task_id = str(content.get("task_id", ""))
    if not task_id:
        return

    csm = get_claude_stream_manager()
    await csm.handle_stream_end(task_id=task_id, result_data=dict(content))


async def _handle_claude_stream_error(
    raw_data: dict[str, object],
    _connection_id: str,
) -> None:
    """Forward claude_stream_error to ClaudeStreamManager."""
    content = raw_data.get("content", {})
    if not isinstance(content, dict):
        return

    task_id = str(content.get("task_id", ""))
    if not task_id:
        return

    csm = get_claude_stream_manager()
    await csm.handle_stream_error(
        task_id=task_id,
        error=str(content.get("error", "Bilinmeyen hata")),
        returncode=int(content.get("returncode", -1)),
    )


# ------------------------------------------------------------------
# Bridge broadcast events (no RPC correlation) — T1.2.
# ------------------------------------------------------------------


async def _handle_usage_report(raw_data: dict[str, object]) -> None:
    """Forward an ``event.usage.report`` envelope to all iOS users.

    The bridge's statusline watcher emits this whenever the local
    ``~/.claude/usage.json`` mod-time advances (see docs/10 §2.11). The
    payload reflects the *current Mac's* claude subscription window and is
    not tied to any particular RPC, so we fan it out to every iOS session
    of every active user.

    Payload field discovery is defensive — the bridge wraps the typed
    ``EventUsageReport`` struct under ``payload`` (preferred) but legacy
    callers may have placed the fields under ``content``.
    """
    body = raw_data.get("payload")
    if not isinstance(body, dict):
        body = raw_data.get("content")
    if not isinstance(body, dict):
        await logger.awarning(
            "usage_report_missing_payload",
            keys=list(raw_data.keys()),
        )
        return

    try:
        five_hour_pct = int(body.get("five_hour_pct", 0))
        seven_day_pct = int(body.get("seven_day_pct", 0))
        five_hour_resets_at = int(body.get("five_hour_resets_at", 0))
        seven_day_resets_at = int(body.get("seven_day_resets_at", 0))
        reported_at = int(body.get("reported_at", 0))
    except (TypeError, ValueError):
        await logger.awarning(
            "usage_report_invalid_payload",
            payload_keys=list(body.keys()),
        )
        return

    # Lazy import — same cycle-avoidance as get_claude_stream_manager.
    from app.api.routes.websocket import manager as ios_manager  # noqa: PLC0415

    csm = get_claude_stream_manager()
    user_ids = ios_manager.get_active_user_ids()
    if not user_ids:
        await logger.adebug("usage_report_no_active_ios_users")
        return

    delivered = 0
    for user_id in user_ids:
        sent = await csm.forward_usage_report(
            user_id=user_id,
            five_hour_pct=five_hour_pct,
            seven_day_pct=seven_day_pct,
            five_hour_resets_at=five_hour_resets_at,
            seven_day_resets_at=seven_day_resets_at,
            reported_at=reported_at,
        )
        delivered += sent

    await logger.ainfo(
        "usage_report_broadcast",
        users=len(user_ids),
        sessions_reached=delivered,
        five_hour_pct=five_hour_pct,
        seven_day_pct=seven_day_pct,
    )


def _extract_event_body(
    raw_data: dict[str, object],
) -> dict[str, object] | None:
    """Return the typed payload of a bridge envelope or ``None``.

    The bridge wraps ``EventStorage*`` structs under ``payload`` (preferred);
    legacy callers may have placed the fields directly under ``content``.
    """
    body = raw_data.get("payload")
    if isinstance(body, dict):
        return body
    body = raw_data.get("content")
    if isinstance(body, dict):
        return body
    return None


async def _resolve_session_owner(session_id: uuid.UUID) -> str | None:
    """Look up the ``user_id`` of the user who owns ``session_id``.

    Returns the stringified UUID (matches the iOS-side ``user_id`` keying
    used by ``ClaudeStreamManager.forward_*``) or ``None`` if the row is
    missing — that case is logged at the call site so orphan events stay
    visible to ops.
    """
    from app.repositories.session_repo import SessionRepository  # noqa: PLC0415

    async with async_session_factory() as session:
        repo = SessionRepository(session)
        record = await repo.get_by_id(session_id)
        if record is None:
            return None
        return str(record.user_id)


async def _handle_session_title(raw_data: dict[str, object]) -> None:
    """Forward an ``event.session.title`` envelope to the session owner.

    The bridge's storage watcher emits this whenever an ``ai-title`` row
    appears in ``~/.claude/projects/<project>/<session>.json`` (see
    docs/10 §6.2). The payload carries a session UUID (per T1.5 contract)
    that we resolve to its owning ``user_id`` via :class:`SessionRepository`,
    then push as a typed ``session.title`` message to all of that user's
    iOS connections.

    Server-side ``generated_at`` injection is delegated to
    :meth:`ClaudeStreamManager.forward_session_title` (T1.5 reviewer M3).
    """
    body = _extract_event_body(raw_data)
    if body is None:
        await logger.awarning(
            "session_title_missing_payload",
            keys=list(raw_data.keys()),
        )
        return

    session_id_raw = body.get("session_id")
    ai_title_raw = body.get("ai_title")
    if not isinstance(session_id_raw, str) or not session_id_raw:
        await logger.awarning(
            "session_title_missing_session_id",
            payload_keys=list(body.keys()),
        )
        return
    if not isinstance(ai_title_raw, str) or not ai_title_raw:
        await logger.awarning(
            "session_title_missing_ai_title",
            session_id=session_id_raw,
        )
        return

    try:
        session_uuid = uuid.UUID(session_id_raw)
    except ValueError:
        await logger.awarning(
            "session_title_invalid_session_id",
            session_id=session_id_raw,
        )
        return

    generated_at_raw = body.get("generated_at")
    generated_at: datetime | None = None
    if isinstance(generated_at_raw, str) and generated_at_raw:
        try:
            generated_at = datetime.fromisoformat(generated_at_raw)
        except ValueError:
            await logger.awarning(
                "session_title_invalid_generated_at",
                session_id=session_id_raw,
                generated_at=generated_at_raw,
            )
            generated_at = None

    user_id = await _resolve_session_owner(session_uuid)
    if user_id is None:
        await logger.awarning(
            "session_title_orphan_session",
            session_id=session_id_raw,
        )
        return

    csm = get_claude_stream_manager()
    sent = await csm.forward_session_title(
        user_id=user_id,
        session_id=session_uuid,
        ai_title=ai_title_raw,
        generated_at=generated_at,
    )
    await logger.ainfo(
        "session_title_forwarded",
        session_id=session_id_raw,
        user_id=user_id,
        sessions_reached=sent,
    )


async def _handle_session_pr_opened(raw_data: dict[str, object]) -> None:
    """Forward an ``event.session.pr_opened`` envelope to the session owner.

    The bridge's storage watcher emits this whenever a ``pr-link`` row
    appears in the session jsonl (typically after ``gh pr create``; see
    docs/10 §6.2). The payload's session UUID is resolved to its owning
    ``user_id`` via :class:`SessionRepository`, then pushed as a typed
    ``session.pr_opened`` message to all of that user's iOS connections.

    Server-side ``opened_at`` injection is delegated to
    :meth:`ClaudeStreamManager.forward_session_pr_opened` (T1.5 reviewer M3).
    """
    body = _extract_event_body(raw_data)
    if body is None:
        await logger.awarning(
            "session_pr_opened_missing_payload",
            keys=list(raw_data.keys()),
        )
        return

    session_id_raw = body.get("session_id")
    pr_url_raw = body.get("pr_url")
    pr_repository_raw = body.get("pr_repository")
    if not isinstance(session_id_raw, str) or not session_id_raw:
        await logger.awarning(
            "session_pr_opened_missing_session_id",
            payload_keys=list(body.keys()),
        )
        return
    if not isinstance(pr_url_raw, str) or not pr_url_raw:
        await logger.awarning(
            "session_pr_opened_missing_pr_url",
            session_id=session_id_raw,
        )
        return
    if not isinstance(pr_repository_raw, str) or not pr_repository_raw:
        await logger.awarning(
            "session_pr_opened_missing_pr_repository",
            session_id=session_id_raw,
        )
        return

    pr_number_raw = body.get("pr_number")
    if not isinstance(pr_number_raw, (int, str)):
        await logger.awarning(
            "session_pr_opened_invalid_pr_number",
            session_id=session_id_raw,
            pr_number_type=type(pr_number_raw).__name__,
        )
        return
    try:
        pr_number = int(pr_number_raw)
    except (TypeError, ValueError):
        await logger.awarning(
            "session_pr_opened_invalid_pr_number",
            session_id=session_id_raw,
            pr_number_raw=pr_number_raw,
        )
        return
    if pr_number <= 0:
        await logger.awarning(
            "session_pr_opened_invalid_pr_number",
            session_id=session_id_raw,
            pr_number=pr_number,
        )
        return

    try:
        session_uuid = uuid.UUID(session_id_raw)
    except ValueError:
        await logger.awarning(
            "session_pr_opened_invalid_session_id",
            session_id=session_id_raw,
        )
        return

    opened_at_raw = body.get("opened_at")
    opened_at: datetime | None = None
    if isinstance(opened_at_raw, str) and opened_at_raw:
        try:
            opened_at = datetime.fromisoformat(opened_at_raw)
        except ValueError:
            await logger.awarning(
                "session_pr_opened_invalid_opened_at",
                session_id=session_id_raw,
                opened_at=opened_at_raw,
            )
            opened_at = None

    user_id = await _resolve_session_owner(session_uuid)
    if user_id is None:
        await logger.awarning(
            "session_pr_opened_orphan_session",
            session_id=session_id_raw,
        )
        return

    csm = get_claude_stream_manager()
    sent = await csm.forward_session_pr_opened(
        user_id=user_id,
        session_id=session_uuid,
        pr_number=pr_number,
        pr_url=pr_url_raw,
        pr_repository=pr_repository_raw,
        opened_at=opened_at,
    )
    await logger.ainfo(
        "session_pr_opened_forwarded",
        session_id=session_id_raw,
        user_id=user_id,
        pr_number=pr_number,
        sessions_reached=sent,
    )
