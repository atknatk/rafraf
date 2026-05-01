"""WebSocket endpoint for iOS client connections."""

from __future__ import annotations

import asyncio
import contextlib
import time
import uuid as _uuid_mod
from datetime import UTC, datetime
from uuid import uuid4

import structlog
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.config import get_settings
from app.core.database import async_session_factory
from app.core.security import SecurityError, verify_access_token
from app.core.websocket import ConnectionManager
from app.orchestrator.claude_code_runner import ToolProgressEvent
from app.orchestrator.question_bridge import get_question_bridge
from app.schemas.approval import ApprovalDecision
from app.schemas.messages import (
    ChatStreamEndPayload,
    ChatStreamPayload,
    ConnectionAckPayload,
    ErrorPayload,
    MessageDirection,
    MessageType,
    ProgressPayload,
    ProgressStepPayload,
    SuggestionPayload,
)
from app.services.agent_registry_service import agent_registry
from app.services.approval_service import get_approval_service
from app.services.conversation_service import ConversationService
from app.services.orchestrator_service import OrchestratorService
from app.services.task_orchestrator_service import TaskOrchestratorService

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

router = APIRouter()

manager = ConnectionManager(heartbeat_interval=30, heartbeat_timeout=10)

# Track active streaming tasks per connection for interrupt support
_active_streams: dict[str, asyncio.Task[object]] = {}

# User-scoped task tracking for reconnect recovery.
# key: "{user_id}:{project_id or 'global'}"
_user_streams: dict[str, asyncio.Task[object]] = {}
_user_connections: dict[str, str] = {}  # user_project_key → current connection_id


def _build_message(
    msg_type: MessageType,
    content: dict[str, object],
    session_id: str | None = None,
) -> dict[str, object]:
    """Build a server-to-client WebSocket message dict."""
    now = datetime.now(tz=UTC).isoformat()
    return {
        "id": str(uuid4()),
        "type": msg_type.value,
        "content": content,
        "metadata": {
            "timestamp": now,
            "session_id": session_id,
            "direction": MessageDirection.SERVER_TO_CLIENT.value,
        },
    }


def _build_error_message(
    error_code: str,
    message: str,
    *,
    details: str | None = None,
    recoverable: bool = True,
    session_id: str | None = None,
) -> dict[str, object]:
    """Build an error message dict."""
    payload = ErrorPayload(
        error_code=error_code,
        message=message,
        details=details,
        recoverable=recoverable,
    )
    return _build_message(
        MessageType.ERROR,
        payload.model_dump(exclude_none=True),
        session_id=session_id,
    )


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(...),
) -> None:
    """Handle iOS client WebSocket connections.

    Authenticates via JWT token passed as query parameter,
    manages heartbeat, and processes JSON messages.
    """
    # --- Authentication ---
    try:
        user_id = verify_access_token(token)
    except SecurityError:
        logger.warning("websocket_auth_failed", reason="invalid_token")
        await websocket.close(code=4008, reason="Invalid token")
        return

    # --- Connection setup ---
    session_id = str(uuid4())
    connection_id = await manager.connect(
        websocket=websocket,
        user_id=user_id,
        session_id=session_id,
    )

    # Send connection acknowledgment
    ack_payload = ConnectionAckPayload(
        user_id=user_id,
        session_id=session_id,
        server_time=datetime.now(tz=UTC).isoformat(),
    )
    ack_message = _build_message(
        MessageType.CONNECTION_ACK,
        ack_payload.model_dump(),
        session_id=session_id,
    )
    await manager.send_json(connection_id, ack_message)

    # Start heartbeat
    await manager.start_heartbeat(connection_id)

    # Re-attach to any in-flight tasks for this user (app closed during processing)
    active_keys = [
        k for k, t in _user_streams.items() if k.startswith(f"{user_id}:") and not t.done()
    ]
    for key in active_keys:
        _user_connections[key] = connection_id
        await manager.send_json(
            connection_id,
            _build_message(
                MessageType.PROGRESS,
                ProgressPayload(
                    task="Önceki sorgunuz hâlâ işleniyor...",
                    step=1,
                    total_steps=1,
                    percentage=50,
                    details="Lütfen bekleyin",
                    phase="starting",
                    steps_detail=[],
                ).model_dump(exclude_none=True),
                session_id=session_id,
            ),
        )
        logger.info(
            "websocket_reattached_to_stream",
            connection_id=connection_id,
            user_id=user_id,
            user_project_key=key,
        )

    logger.info(
        "websocket_session_started",
        connection_id=connection_id,
        user_id=user_id,
        session_id=session_id,
    )

    # --- Message loop ---
    try:
        while True:
            raw_data: dict[str, object] = await websocket.receive_json()
            await _handle_message(raw_data, connection_id, session_id, user_id)
    except WebSocketDisconnect:
        logger.info(
            "websocket_client_disconnected",
            connection_id=connection_id,
            user_id=user_id,
        )
    except Exception:
        logger.exception(
            "websocket_unexpected_error",
            connection_id=connection_id,
            user_id=user_id,
        )
    finally:
        await manager.disconnect(connection_id)


async def _handle_message(
    raw_data: dict[str, object],
    connection_id: str,
    session_id: str,
    user_id: str,
) -> None:
    """Route an incoming message to the appropriate handler."""
    msg_type_raw = raw_data.get("type")
    if not isinstance(msg_type_raw, str):
        error_msg = _build_error_message(
            error_code="INVALID_MESSAGE",
            message="Message must have a 'type' field",
            session_id=session_id,
        )
        await manager.send_json(connection_id, error_msg)
        return

    try:
        msg_type = MessageType(msg_type_raw)
    except ValueError:
        error_msg = _build_error_message(
            error_code="UNKNOWN_MESSAGE_TYPE",
            message=f"Unknown message type: {msg_type_raw}",
            details=f"Supported types: {', '.join(t.value for t in MessageType)}",
            session_id=session_id,
        )
        await manager.send_json(connection_id, error_msg)
        return

    logger.info(
        "websocket_message_received",
        connection_id=connection_id,
        user_id=user_id,
        message_type=msg_type.value,
    )

    if msg_type == MessageType.PONG:
        await _handle_pong(connection_id)
    elif msg_type == MessageType.PING:
        await _handle_client_ping(raw_data, connection_id, session_id)
    elif msg_type == MessageType.TEXT:
        await _handle_text(raw_data, connection_id, session_id, user_id)
    elif msg_type == MessageType.APPROVAL_RESPONSE:
        await _handle_approval_response(raw_data, connection_id, session_id)
    elif msg_type == MessageType.CANCEL_STREAM:
        await _handle_cancel_stream(connection_id, session_id)
    else:
        error_msg = _build_error_message(
            error_code="UNSUPPORTED_CLIENT_MESSAGE",
            message=f"Message type '{msg_type.value}' is not accepted from clients",
            session_id=session_id,
        )
        await manager.send_json(connection_id, error_msg)


async def _handle_cancel_stream(connection_id: str, session_id: str) -> None:
    """Cancel the active AI stream for this connection."""
    task = _active_streams.get(connection_id)
    if task is not None and not task.done():
        task.cancel()
        logger.info("stream_cancelled_by_user", connection_id=connection_id)
    # Send typing.end so iOS clears the indicator, then cancelled ack
    with contextlib.suppress(Exception):
        await manager.send_json(
            connection_id,
            _build_message(MessageType.TYPING_END, {}, session_id=session_id),
        )
    with contextlib.suppress(Exception):
        await manager.send_json(
            connection_id,
            _build_message(
                MessageType.STREAM_CANCELLED,
                {"message": "Stream iptal edildi"},
                session_id=session_id,
            ),
        )


async def _handle_pong(connection_id: str) -> None:
    """Process a pong message (heartbeat response)."""
    logger.debug("heartbeat_pong_received", connection_id=connection_id)


async def _handle_client_ping(
    _raw_data: dict[str, object],
    connection_id: str,
    session_id: str,
) -> None:
    """Respond to a client-initiated ping with a pong."""
    pong_data: dict[str, object] = {
        "id": str(uuid4()),
        "type": MessageType.PONG.value,
        "content": {
            "timestamp": datetime.now(tz=UTC).isoformat(),
        },
        "metadata": {
            "timestamp": datetime.now(tz=UTC).isoformat(),
            "session_id": session_id,
            "direction": MessageDirection.SERVER_TO_CLIENT.value,
        },
    }
    await manager.send_json(connection_id, pong_data)


def _extract_project_id(raw_data: dict[str, object]) -> str | None:
    """Extract project_id from message metadata (iOS sends as projectId)."""
    metadata = raw_data.get("metadata")
    if not isinstance(metadata, dict):
        return None
    project_id = metadata.get("projectId") or metadata.get("project_id")
    if project_id is not None and not isinstance(project_id, str):
        return str(project_id)
    return project_id


def _extract_agent_id(raw_data: dict[str, object]) -> str | None:
    """Extract agent_id from message metadata (iOS sends as agentId)."""
    metadata = raw_data.get("metadata")
    if not isinstance(metadata, dict):
        return None
    agent_id = metadata.get("agentId") or metadata.get("agent_id")
    if agent_id is not None and not isinstance(agent_id, str):
        return str(agent_id)
    return agent_id


async def _handle_text(
    raw_data: dict[str, object],
    connection_id: str,
    session_id: str,
    user_id: str,
) -> None:
    """Process a text message from the client via AI orchestrator."""
    content = raw_data.get("content", "")
    if not isinstance(content, str):
        content = str(content)

    project_id = _extract_project_id(raw_data)
    agent_id = _extract_agent_id(raw_data)

    logger.info(
        "text_message_received",
        connection_id=connection_id,
        user_id=user_id,
        content_length=len(content),
        project_id=project_id,
        agent_id=agent_id,
    )

    # Route through AI orchestrator
    await _process_with_orchestrator(
        message=content,
        connection_id=connection_id,
        session_id=session_id,
        user_id=user_id,
        project_id=project_id,
        agent_id=agent_id,
    )


async def _build_host_status() -> str | None:
    """Build formatted agent status string for system prompt injection."""
    agent_list = await agent_registry.list_agents()
    if not agent_list.agents:
        return None

    lines: list[str] = []
    for agent in agent_list.agents:
        caps = ", ".join(c.value for c in agent.capabilities)
        status_str = agent.status.value
        resource_str = ""
        if agent.resources is not None:
            resource_str = (
                f" | CPU {agent.resources.cpu_usage_percent:.0f}%"
                f", RAM {agent.resources.memory_usage_percent:.0f}%"
            )
        tasks_str = f", tasks: {agent.active_tasks}" if agent.active_tasks else ""
        lines.append(
            f"- {agent.host_id}: {status_str}{resource_str}{tasks_str} | capabilities: [{caps}]"
        )

    return "\n".join(lines)


class _TaskWSAdapter:
    """Adapter: ConnectionManager.send_to_user as broadcast_to_user for TaskOrchestrator."""

    def __init__(self, conn_manager: ConnectionManager) -> None:
        self._manager = conn_manager

    async def broadcast_to_user(
        self, user_id: str | _uuid_mod.UUID, message: dict[str, object]
    ) -> int:
        """Broadcast a message to all connections of a user."""
        uid = str(user_id)
        return await self._manager.send_to_user(uid, message)


async def _task_orch_update_progress(
    task_id: _uuid_mod.UUID,
    step: str,
    pct: int,
    detail: str,
) -> None:
    """Update task progress using a fresh DB session."""
    try:
        async with async_session_factory() as db:
            orch = TaskOrchestratorService(db=db, ws_manager=_TaskWSAdapter(manager))
            # Load task from DB into in-memory store
            from sqlalchemy import select

            from app.models.task import Task

            result = await db.execute(select(Task).where(Task.id == task_id))
            task = result.scalar_one_or_none()
            if task is not None:
                orch._tasks[task.id] = task
                await orch.update_progress(task_id=task_id, step=step, pct=pct, detail=detail)
    except Exception:
        logger.warning("task_orch_update_progress_failed", task_id=str(task_id))


async def _task_orch_complete(task_id: _uuid_mod.UUID, summary: str) -> None:
    """Complete a task using a fresh DB session."""
    try:
        async with async_session_factory() as db:
            orch = TaskOrchestratorService(db=db, ws_manager=_TaskWSAdapter(manager))
            from sqlalchemy import select

            from app.models.task import Task

            result = await db.execute(select(Task).where(Task.id == task_id))
            task = result.scalar_one_or_none()
            if task is not None:
                orch._tasks[task.id] = task
                await orch.complete_task(task_id=task_id, summary=summary)
    except Exception:
        logger.warning("task_orch_complete_failed", task_id=str(task_id))


async def _task_orch_fail(task_id: _uuid_mod.UUID, error: str) -> None:
    """Fail a task using a fresh DB session."""
    try:
        async with async_session_factory() as db:
            orch = TaskOrchestratorService(db=db, ws_manager=_TaskWSAdapter(manager))
            from sqlalchemy import select

            from app.models.task import Task

            result = await db.execute(select(Task).where(Task.id == task_id))
            task = result.scalar_one_or_none()
            if task is not None:
                orch._tasks[task.id] = task
                await orch.fail_task(task_id=task_id, error=error)
    except Exception:
        logger.warning("task_orch_fail_failed", task_id=str(task_id))


async def _process_with_orchestrator(
    *,
    message: str,
    connection_id: str,
    session_id: str,
    user_id: str,
    project_id: str | None = None,
    agent_id: str | None = None,
) -> None:
    """Process a message through claude -p or API fallback.

    Primary path: claude -p subprocess (Max subscription, $0).
    Fallback path: Bedrock/Anthropic API (per-token).

    Streams text deltas via chat.stream messages as Claude generates tokens.
    """
    settings = get_settings()
    message_id = str(uuid4())

    # Task orchestrator state — mutable container so callbacks can access task_id
    _task_id_ref: list[_uuid_mod.UUID | None] = [None]

    # Stream-based progress tracking for Live Activity
    _stream_char_count: list[int] = [0]
    _stream_first_token_sent: list[bool] = [False]
    _stream_first_writing_sent: list[bool] = [False]
    _stream_last_progress_chars: list[int] = [0]
    _stream_last_progress_time: list[float] = [0.0]
    _stream_has_tool_progress: list[bool] = [False]
    _stream_progress_char_interval = 150  # send progress every N chars
    _stream_progress_min_interval_sec = 1.0  # min seconds between updates

    # User-scoped key for reconnect recovery
    user_project_key = f"{user_id}:{project_id or 'global'}"
    _user_connections[user_project_key] = connection_id

    # --- Progress: islem basladi ---
    startup_progress = _build_message(
        MessageType.PROGRESS,
        ProgressPayload(
            task="Sorgunuz işleniyor...",
            step=1,
            total_steps=3,
            percentage=5,
            details="Başlanıyor",
            phase="starting",
            steps_detail=[],
        ).model_dump(exclude_none=True),
        session_id=session_id,
    )
    await manager.send_json(connection_id, startup_progress)

    # Typing indicator — Claude is thinking
    with contextlib.suppress(Exception):
        await manager.send_json(
            connection_id,
            _build_message(MessageType.TYPING_START, {}, session_id=session_id),
        )

    # --- Callbacks ---

    def _current_conn() -> str:
        """Return the current active connection for this user+project (supports reconnect)."""
        return _user_connections.get(user_project_key, connection_id)

    async def _on_text_delta(delta: str, index: int) -> None:
        """Send streaming text delta to client."""
        stream_msg = _build_message(
            MessageType.CHAT_STREAM,
            ChatStreamPayload(
                message_id=message_id,
                delta=delta,
                index=index,
            ).model_dump(),
            session_id=session_id,
        )
        with contextlib.suppress(Exception):
            await manager.send_json(_current_conn(), stream_msg)

        # --- Stream-based Live Activity progress ---
        _tid = _task_id_ref[0]
        if _tid is not None and not _stream_has_tool_progress[0]:
            _stream_char_count[0] += len(delta)

            now = time.monotonic()
            if not _stream_first_token_sent[0]:
                # First token arrived → "Analyzing"
                _stream_first_token_sent[0] = True
                _stream_last_progress_time[0] = now
                await _task_orch_update_progress(
                    task_id=_tid,
                    step="analyzing",
                    pct=15,
                    detail="İstek analiz ediliyor...",
                )
            elif not _stream_first_writing_sent[0] and _stream_char_count[0] >= 80:
                # First writing update — no time throttle, just 80 chars
                _stream_first_writing_sent[0] = True
                _stream_last_progress_chars[0] = _stream_char_count[0]
                _stream_last_progress_time[0] = now
                await _task_orch_update_progress(
                    task_id=_tid,
                    step="writing",
                    pct=25,
                    detail="Yanıt yazılıyor...",
                )
            elif (
                _stream_first_writing_sent[0]
                and _stream_char_count[0] - _stream_last_progress_chars[0]
                >= _stream_progress_char_interval
                and now - _stream_last_progress_time[0] >= _stream_progress_min_interval_sec
            ):
                # Periodic progress: 30% → 80% based on char count (throttled)
                _stream_last_progress_chars[0] = _stream_char_count[0]
                _stream_last_progress_time[0] = now
                # Smooth progress: asymptotic approach to 80%
                pct = min(80, 30 + int(50 * (1 - 1 / (1 + _stream_char_count[0] / 600))))
                await _task_orch_update_progress(
                    task_id=_tid,
                    step="writing",
                    pct=pct,
                    detail="Yanıt yazılıyor...",
                )

    async def _on_stream_end(_full_text: str) -> None:
        """Finalize streaming: send stream end progress update."""
        # --- Stream-based Live Activity: finalizing phase ---
        _tid = _task_id_ref[0]
        if _tid is not None:
            await _task_orch_update_progress(
                task_id=_tid,
                step="finalizing",
                pct=90,
                detail="Tamamlanıyor...",
            )

    async def _on_tool_progress(event: ToolProgressEvent) -> None:
        """Send detailed progress to iOS."""
        steps_payload = [
            ProgressStepPayload(
                id=s.id,
                step_type=s.step_type,
                label=s.label,
                status=s.status,
                tool_name=s.tool_name,
                duration_seconds=s.duration_seconds,
                detail=s.detail,
            )
            for s in event.steps
        ]
        active_idx = next(
            (i for i, s in enumerate(event.steps) if s.status == "active"),
            len(event.steps) - 1,
        )
        progress_msg = _build_message(
            MessageType.PROGRESS,
            ProgressPayload(
                task=event.phase_label,
                step=active_idx + 1,
                total_steps=len(event.steps),
                percentage=event.percentage,
                details=(f"Tool: {event.current_tool}" if event.current_tool else None),
                phase=event.phase,
                steps_detail=steps_payload,
            ).model_dump(exclude_none=True),
            session_id=session_id,
        )
        with contextlib.suppress(Exception):
            await manager.send_json(_current_conn(), progress_msg)

        # Update task orchestrator progress (non-blocking)
        _tid = _task_id_ref[0]
        if _tid is not None:
            _stream_has_tool_progress[0] = True  # disable stream-based progress
            step_name = event.current_tool or event.phase
            await _task_orch_update_progress(
                task_id=_tid,
                step=step_name,
                pct=event.percentage,
                detail=event.phase_label,
            )

    async def _on_question(question_payload: dict[str, object]) -> str | None:
        """Forward question to iOS and wait for answer."""
        bridge = get_question_bridge()

        async def _send_to_ios(msg: dict[str, object]) -> None:
            with contextlib.suppress(Exception):
                await manager.send_json(_current_conn(), msg)

        return await bridge.ask_user(
            question_payload=question_payload,
            send_to_ios=_send_to_ios,
            session_id=session_id,
        )

    # --- Ana islem ---

    async def _run_processing() -> None:
        response_text = ""
        model_used = "none"
        tokens_in = 0
        tokens_out = 0

        # --- Create task in orchestrator (optional, non-breaking) ---
        try:
            async with async_session_factory() as _task_db:
                _user_uuid = _uuid_mod.UUID(user_id) if isinstance(user_id, str) else user_id
                _proj_uuid_for_task: _uuid_mod.UUID | None = None
                if project_id:
                    with contextlib.suppress(ValueError):
                        _proj_uuid_for_task = _uuid_mod.UUID(project_id)

                _ws_adapter = _TaskWSAdapter(manager)
                task_orch = TaskOrchestratorService(
                    db=_task_db,
                    ws_manager=_ws_adapter,
                )

                task_obj = await task_orch.create_task(
                    user_id=_user_uuid,
                    project_id=_proj_uuid_for_task,
                    prompt=message,
                    task_type="chat",
                )
                task_obj.title = message[:100]
                task_obj.total_steps = 1  # chat = single step
                await _task_db.commit()
                _task_id_ref[0] = task_obj.id

                await task_orch.start_task(task_obj.id)

                # Immediately send "thinking" phase so user sees activity
                await task_orch.update_progress(
                    task_id=task_obj.id,
                    step="thinking",
                    pct=5,
                    detail="Düşünüyor...",
                )
                logger.info(
                    "task_created_for_chat",
                    task_id=str(task_obj.id),
                    user_id=user_id,
                )
        except Exception:
            logger.warning(
                "task_creation_failed_continuing",
                user_id=user_id,
                session_id=session_id,
            )

        try:
            # Persist user message
            try:
                async with async_session_factory() as _db:
                    await ConversationService(_db).save_message(
                        session_id=session_id,
                        user_id=user_id,
                        role="user",
                        content=message,
                        project_id=_project_uuid,
                        agent_id=agent_id,
                    )
                    await _db.commit()
            except Exception:
                logger.warning("user_message_save_failed", session_id=session_id)

            orchestrator = OrchestratorService()

            if settings.claude_code_enabled:
                # --- PRIMARY PATH: claude -p ---
                async with async_session_factory() as _proj_db:
                    response = await orchestrator.process_with_claude_code(
                        session_id=session_id,
                        user_id=user_id,
                        message=message,
                        project_id=project_id,
                        db_session=_proj_db,
                        on_text_delta=_on_text_delta,
                        on_stream_end=_on_stream_end,
                        on_tool_progress=_on_tool_progress,
                        on_question=_on_question,
                    )
            else:
                # --- FALLBACK PATH: API ---
                host_status = await _build_host_status()
                response = await orchestrator.process_user_message_streaming(
                    session_id=session_id,
                    user_id=user_id,
                    message=message,
                    project_id=project_id,
                    on_text_delta=_on_text_delta,
                    on_stream_end=_on_stream_end,
                    progress_callback=lambda name, _step, _total: _on_tool_progress(
                        ToolProgressEvent(
                            phase="tool_calling",
                            phase_label=f"Calisiyor: {name}",
                            current_tool=name,
                            percentage=50,
                            steps=[],
                        )
                    ),
                    host_status=host_status,
                )

            response_text = response.response_text
            model_used = response.model_used
            tokens_in = response.tokens_input
            tokens_out = response.tokens_output

            # Persist assistant response
            try:
                async with async_session_factory() as _db:
                    await ConversationService(_db).save_message(
                        session_id=session_id,
                        user_id=user_id,
                        role="assistant",
                        content=response_text,
                        project_id=_project_uuid,
                        agent_id=agent_id,
                        model_used=model_used,
                        tokens_used=tokens_out,
                    )
                    await _db.commit()
            except Exception:
                logger.warning("assistant_message_save_failed", session_id=session_id)

            # CODE_DIFF: proje degisikliklerini gonder
            if project_id and response_text:
                try:
                    from app.services.git_diff_service import get_project_diff
                    from app.services.project_service import ProjectService

                    async with async_session_factory() as _diff_db:
                        _diff_project_uuid = _uuid_mod.UUID(project_id)
                        _diff_detail = await ProjectService(_diff_db).get_project_by_id(
                            _diff_project_uuid
                        )
                        diff_path = _diff_detail.local_path
                    if diff_path:
                        diff_payload = await get_project_diff(diff_path)
                        if diff_payload is not None:
                            diff_msg = _build_message(
                                MessageType.CODE_DIFF,
                                diff_payload.model_dump(),
                                session_id=session_id,
                            )
                            with contextlib.suppress(Exception):
                                await manager.send_json(_current_conn(), diff_msg)
                except Exception:
                    logger.warning("code_diff_send_failed", session_id=session_id)

        except Exception as _exc:
            logger.exception(
                "run_processing_failed",
                connection_id=connection_id,
                session_id=session_id,
            )
            if not response_text:
                response_text = "Bir hata olustu. Lutfen tekrar deneyin."

            # Mark task as failed (non-breaking)
            _tid = _task_id_ref[0]
            if _tid is not None:
                await _task_orch_fail(_tid, error=str(_exc))
        else:
            # Mark task as completed (non-breaking)
            _tid = _task_id_ref[0]
            if _tid is not None and response_text:
                await _task_orch_complete(_tid, summary=response_text[:500])

        # Typing indicator cleared — response ready
        with contextlib.suppress(Exception):
            await manager.send_json(
                _current_conn(),
                _build_message(MessageType.TYPING_END, {}, session_id=session_id),
            )

        # ALWAYS send CHAT_STREAM_END so the client never hangs
        end_msg = _build_message(
            MessageType.CHAT_STREAM_END,
            ChatStreamEndPayload(
                message_id=message_id,
                full_text=response_text,
                model_used=model_used,
                tokens_used={
                    "input": tokens_in,
                    "output": tokens_out,
                },
            ).model_dump(),
            session_id=session_id,
        )
        try:
            await manager.send_json(_current_conn(), end_msg)
        except Exception:
            logger.warning(
                "chat_stream_end_send_failed",
                connection_id=connection_id,
            )

        # Suggestions: arka planda uret ve gonder (fire-and-forget)
        if response_text:

            async def _send_suggestions() -> None:
                try:
                    from app.services.suggestion_service import generate_suggestions

                    suggestions = await generate_suggestions(
                        user_message=message,
                        ai_response=response_text,
                    )
                    if suggestions:
                        sugg_msg = _build_message(
                            MessageType.SUGGESTION,
                            SuggestionPayload(
                                message_id=message_id,
                                suggestions=suggestions,
                            ).model_dump(),
                            session_id=session_id,
                        )
                        await manager.send_json(_current_conn(), sugg_msg)
                except Exception:
                    logger.warning("suggestions_send_failed", session_id=session_id)

            asyncio.create_task(_send_suggestions())

    # Parse project_id as UUID for DB storage
    _project_uuid: _uuid_mod.UUID | None = None
    if project_id:
        with contextlib.suppress(ValueError):
            _project_uuid = _uuid_mod.UUID(project_id)

    # Run as cancellable task; track by user+project for reconnect recovery
    task = asyncio.create_task(_run_processing())
    _active_streams[connection_id] = task
    _user_streams[user_project_key] = task

    try:
        await task
    except asyncio.CancelledError:
        logger.info(
            "streaming_interrupted",
            connection_id=connection_id,
            session_id=session_id,
        )
    except Exception:
        logger.exception(
            "process_orchestrator_task_failed",
            connection_id=connection_id,
            session_id=session_id,
        )
    finally:
        _active_streams.pop(connection_id, None)
        _user_streams.pop(user_project_key, None)
        _user_connections.pop(user_project_key, None)


async def _handle_approval_response(
    raw_data: dict[str, object],
    connection_id: str,
    session_id: str,
) -> None:
    """Process an approval response from the client.

    Extracts the decision payload and submits it to the approval service.
    """
    content = raw_data.get("content")
    if not isinstance(content, dict):
        error_msg = _build_error_message(
            error_code="INVALID_APPROVAL_RESPONSE",
            message="approval_response content must be a JSON object",
            session_id=session_id,
        )
        await manager.send_json(connection_id, error_msg)
        return

    approval_id = content.get("approval_id")
    decision_str = content.get("decision")

    if not isinstance(approval_id, str) or not isinstance(decision_str, str):
        error_msg = _build_error_message(
            error_code="INVALID_APPROVAL_RESPONSE",
            message="approval_response must contain 'approval_id' and 'decision' strings",
            session_id=session_id,
        )
        await manager.send_json(connection_id, error_msg)
        return

    if decision_str not in ("approved", "rejected"):
        error_msg = _build_error_message(
            error_code="INVALID_APPROVAL_DECISION",
            message=f"Invalid decision: {decision_str}. Must be 'approved' or 'rejected'",
            session_id=session_id,
        )
        await manager.send_json(connection_id, error_msg)
        return

    note = content.get("note")
    note_str = str(note) if note is not None else None

    decision = ApprovalDecision(
        approval_id=approval_id,
        decision=decision_str,
        note=note_str,
    )

    approval_service = get_approval_service()
    submitted = await approval_service.submit_decision(decision)

    # Also check QuestionBridge for claude -p questions
    if not submitted:
        bridge = get_question_bridge()
        note_answer = note_str or decision_str
        bridge_submitted = bridge.submit_answer(approval_id, note_answer)
        if bridge_submitted:
            logger.info(
                "question_bridge_answer_submitted",
                approval_id=approval_id,
                answer=note_answer[:100] if note_answer else "",
            )
        else:
            error_msg = _build_error_message(
                error_code="APPROVAL_NOT_FOUND",
                message=f"No pending approval found with ID: {approval_id}",
                session_id=session_id,
            )
            await manager.send_json(connection_id, error_msg)

    logger.info(
        "approval_response_received",
        connection_id=connection_id,
        approval_id=approval_id,
        decision=decision_str,
        submitted=submitted,
    )
