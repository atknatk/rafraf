"""WebSocket endpoint for iOS client connections."""

from __future__ import annotations

import asyncio
import contextlib
import uuid as _uuid_mod
from datetime import UTC, datetime
from typing import TYPE_CHECKING
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
    VoiceAudioChunkPayload,
)
from app.services.agent_registry_service import agent_registry
from app.services.approval_service import get_approval_service
from app.services.conversation_service import ConversationService
from app.services.orchestrator_service import OrchestratorService

if TYPE_CHECKING:
    from app.services.tts_service import TTSService

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
        await logger.awarning("websocket_auth_failed", reason="invalid_token")
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
    active_keys = [k for k, t in _user_streams.items() if k.startswith(f"{user_id}:") and not t.done()]
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
        await logger.ainfo(
            "websocket_reattached_to_stream",
            connection_id=connection_id,
            user_id=user_id,
            user_project_key=key,
        )

    await logger.ainfo(
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
        await logger.ainfo(
            "websocket_client_disconnected",
            connection_id=connection_id,
            user_id=user_id,
        )
    except Exception:
        await logger.aexception(
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

    await logger.ainfo(
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
    elif msg_type == MessageType.VOICE:
        await _handle_voice(raw_data, connection_id, session_id, user_id)
    elif msg_type == MessageType.APPROVAL_RESPONSE:
        await _handle_approval_response(raw_data, connection_id, session_id)
    elif msg_type == MessageType.VOICE_INTERRUPT:
        await _handle_voice_interrupt(connection_id)
    else:
        error_msg = _build_error_message(
            error_code="UNSUPPORTED_CLIENT_MESSAGE",
            message=f"Message type '{msg_type.value}' is not accepted from clients",
            session_id=session_id,
        )
        await manager.send_json(connection_id, error_msg)


async def _handle_pong(connection_id: str) -> None:
    """Process a pong message (heartbeat response)."""
    await logger.adebug("heartbeat_pong_received", connection_id=connection_id)


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

    await logger.ainfo(
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


async def _handle_voice(
    raw_data: dict[str, object],
    connection_id: str,
    session_id: str,
    user_id: str,
) -> None:
    """Process a voice message from the client via AI orchestrator.

    Voice content is assumed to already be transcribed (STT done client-side or
    by a separate service). The transcribed text is routed to the orchestrator.
    """
    content = raw_data.get("content", "")
    if not isinstance(content, str):
        content = str(content)

    project_id = _extract_project_id(raw_data)
    agent_id = _extract_agent_id(raw_data)

    await logger.ainfo(
        "voice_message_received",
        connection_id=connection_id,
        user_id=user_id,
        project_id=project_id,
        agent_id=agent_id,
    )

    # Route through AI orchestrator (transcribed text) with TTS streaming
    await _process_with_orchestrator(
        message=content,
        connection_id=connection_id,
        session_id=session_id,
        user_id=user_id,
        voice_mode=True,
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


async def _process_with_orchestrator(
    *,
    message: str,
    connection_id: str,
    session_id: str,
    user_id: str,
    voice_mode: bool = False,
    project_id: str | None = None,
    agent_id: str | None = None,
) -> None:
    """Process a message through claude -p or API fallback.

    Primary path: claude -p subprocess (Max subscription, $0).
    Fallback path: Bedrock/Anthropic API (per-token).

    Streams text deltas via chat.stream messages as Claude generates tokens.
    Optionally generates TTS audio chunks for voice mode.
    """
    settings = get_settings()
    message_id = str(uuid4())
    tts_service = None
    sentence_acc = None

    if voice_mode:
        from app.services.tts_service import SentenceAccumulator, TTSService

        tts_service = TTSService()
        sentence_acc = SentenceAccumulator()

    tts_tasks: list[asyncio.Task[None]] = []
    chunk_index = 0

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
        nonlocal chunk_index
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

        # TTS: accumulate sentences and send audio chunks
        if tts_service is not None and sentence_acc is not None:
            sentences = sentence_acc.add(delta)
            for sentence in sentences:
                ci = chunk_index
                chunk_index += 1
                task = asyncio.create_task(
                    _send_tts_chunk(
                        tts_service,
                        sentence,
                        message_id,
                        ci,
                        connection_id,
                        session_id,
                    )
                )
                tts_tasks.append(task)

    async def _on_stream_end(_full_text: str) -> None:
        """Finalize streaming: flush TTS buffer, send stream end."""
        nonlocal chunk_index

        if tts_service is not None and sentence_acc is not None:
            remaining = sentence_acc.flush()
            if remaining:
                ci = chunk_index
                chunk_index += 1
                task = asyncio.create_task(
                    _send_tts_chunk(
                        tts_service,
                        remaining,
                        message_id,
                        ci,
                        connection_id,
                        session_id,
                        is_last=True,
                    )
                )
                tts_tasks.append(task)

        if tts_tasks:
            await asyncio.gather(*tts_tasks, return_exceptions=True)

        if tts_service is not None:
            audio_end_msg = _build_message(
                MessageType.VOICE_AUDIO_END,
                {"message_id": message_id},
                session_id=session_id,
            )
            with contextlib.suppress(Exception):
                await manager.send_json(_current_conn(), audio_end_msg)

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
                await logger.awarning("user_message_save_failed", session_id=session_id)

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
                await logger.awarning("assistant_message_save_failed", session_id=session_id)

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
                    await logger.awarning("code_diff_send_failed", session_id=session_id)

            # Save conversation turn to mem0 (fire-and-forget, non-blocking)
            if response_text:
                asyncio.create_task(_save_turn_to_memory(
                    user_id=user_id,
                    session_id=session_id,
                    user_message=message,
                    assistant_response=response_text,
                ))

        except Exception:
            await logger.aexception(
                "run_processing_failed",
                connection_id=connection_id,
                session_id=session_id,
            )
            if not response_text:
                response_text = "Bir hata olustu. Lutfen tekrar deneyin."

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
            await logger.awarning(
                "chat_stream_end_send_failed",
                connection_id=connection_id,
            )

        # Suggestions: arka planda uret ve gonder (fire-and-forget, voice modda degil)
        if response_text and not voice_mode:
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
                    await logger.awarning("suggestions_send_failed", session_id=session_id)

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
        await logger.ainfo(
            "streaming_interrupted",
            connection_id=connection_id,
            session_id=session_id,
        )
        for tts_task in tts_tasks:
            if not tts_task.done():
                tts_task.cancel()
    except Exception:
        await logger.aexception(
            "process_orchestrator_task_failed",
            connection_id=connection_id,
            session_id=session_id,
        )
    finally:
        _active_streams.pop(connection_id, None)
        _user_streams.pop(user_project_key, None)
        _user_connections.pop(user_project_key, None)


async def _save_turn_to_memory(
    user_id: str,
    session_id: str,
    user_message: str,
    assistant_response: str,
) -> None:
    """Save a conversation turn to mem0 personal memory (Layer 3). Fire-and-forget."""
    from app.services.memory_service import MemoryServiceError, memory_service

    try:
        await memory_service.save_conversation_facts(
            user_id=user_id,
            session_id=session_id,
            messages=[
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": assistant_response},
            ],
        )
        await logger.adebug("turn_memory_saved", user_id=user_id, session_id=session_id)
    except MemoryServiceError:
        await logger.awarning("turn_memory_save_failed", user_id=user_id)
    except Exception:
        await logger.awarning("turn_memory_save_unexpected", user_id=user_id)


async def _send_tts_chunk(
    tts_service: TTSService,
    sentence: str,
    message_id: str,
    chunk_index: int,
    connection_id: str,
    session_id: str,
    *,
    is_last: bool = False,
) -> None:
    """Generate TTS for a sentence and send audio chunk over WebSocket."""
    import base64

    try:
        audio_bytes = await tts_service.synthesize_sentence(sentence)
        audio_b64 = base64.b64encode(audio_bytes).decode("ascii")

        chunk_payload = VoiceAudioChunkPayload(
            message_id=message_id,
            chunk_index=chunk_index,
            audio_data=audio_b64,
            sentence_text=sentence,
            is_last_chunk=is_last,
        )
        chunk_msg = _build_message(
            MessageType.VOICE_AUDIO_CHUNK,
            chunk_payload.model_dump(),
            session_id=session_id,
        )
        await manager.send_json(connection_id, chunk_msg)
    except Exception:
        await logger.aexception(
            "tts_chunk_failed",
            sentence=sentence[:50],
            chunk_index=chunk_index,
        )


async def _handle_voice_interrupt(connection_id: str) -> None:
    """Cancel active streaming for a connection (barge-in)."""
    task = _active_streams.get(connection_id)
    if task and not task.done():
        task.cancel()
        await logger.ainfo("voice_stream_interrupted", connection_id=connection_id)


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
            await logger.ainfo(
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

    await logger.ainfo(
        "approval_response_received",
        connection_id=connection_id,
        approval_id=approval_id,
        decision=decision_str,
        submitted=submitted,
    )
