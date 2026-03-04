"""WebSocket endpoint for iOS client connections."""

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import structlog
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.security import SecurityError, verify_access_token
from app.core.websocket import ConnectionManager
from app.schemas.approval import ApprovalDecision
from app.schemas.messages import (
    ChatStreamEndPayload,
    ChatStreamPayload,
    ConnectionAckPayload,
    ErrorPayload,
    MessageDirection,
    MessageType,
    ProgressPayload,
    VoiceAudioChunkPayload,
)
from app.schemas.agent import AgentStatus
from app.services.agent_registry_service import agent_registry
from app.services.approval_service import get_approval_service
from app.services.orchestrator_service import OrchestratorService

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

router = APIRouter()

manager = ConnectionManager(heartbeat_interval=30, heartbeat_timeout=10)

# Track active streaming tasks per connection for interrupt support
_active_streams: dict[str, asyncio.Task[object]] = {}


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

    await logger.ainfo(
        "text_message_received",
        connection_id=connection_id,
        user_id=user_id,
        content_length=len(content),
    )

    # Route through AI orchestrator
    await _process_with_orchestrator(
        message=content,
        connection_id=connection_id,
        session_id=session_id,
        user_id=user_id,
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

    await logger.ainfo(
        "voice_message_received",
        connection_id=connection_id,
        user_id=user_id,
    )

    # Route through AI orchestrator (transcribed text) with TTS streaming
    await _process_with_orchestrator(
        message=content,
        connection_id=connection_id,
        session_id=session_id,
        user_id=user_id,
        voice_mode=True,
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
            f"- {agent.host_id}: {status_str}{resource_str}{tasks_str}"
            f" | capabilities: [{caps}]"
        )

    return "\n".join(lines)


async def _process_with_orchestrator(
    *,
    message: str,
    connection_id: str,
    session_id: str,
    user_id: str,
    voice_mode: bool = False,
) -> None:
    """Process a message through the AI orchestrator with streaming response.

    Streams text deltas via chat.stream messages as Claude generates tokens.
    Optionally generates TTS audio chunks for voice mode.
    """
    orchestrator = OrchestratorService()
    message_id = str(uuid4())
    tts_service = None
    sentence_acc = None

    if voice_mode:
        from app.services.tts_service import SentenceAccumulator, TTSService

        tts_service = TTSService()
        sentence_acc = SentenceAccumulator()

    tts_tasks: list[asyncio.Task[None]] = []
    chunk_index = 0

    async def _progress_callback(tool_name: str, step: int, total_steps: int) -> None:
        """Send progress update to the client during tool execution."""
        progress_payload = ProgressPayload(
            task=f"Tool calisiyor: {tool_name}",
            step=step,
            total_steps=total_steps,
            percentage=int((step / total_steps) * 100),
            details=f"Executing {tool_name}",
        )
        progress_msg = _build_message(
            MessageType.PROGRESS,
            progress_payload.model_dump(exclude_none=True),
            session_id=session_id,
        )
        await manager.send_json(connection_id, progress_msg)

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
        await manager.send_json(connection_id, stream_msg)

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

    async def _on_stream_end(full_text: str) -> None:
        """Finalize streaming: flush TTS buffer, send stream end."""
        nonlocal chunk_index

        # Flush remaining sentence buffer for TTS
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

        # Wait for all TTS tasks to complete
        if tts_tasks:
            await asyncio.gather(*tts_tasks, return_exceptions=True)

        # Send voice audio end signal
        if tts_service is not None:
            audio_end_msg = _build_message(
                MessageType.VOICE_AUDIO_END,
                {"message_id": message_id},
                session_id=session_id,
            )
            await manager.send_json(connection_id, audio_end_msg)

    # Build agent status for system prompt
    host_status = await _build_host_status()

    # Create cancellable streaming task
    async def _run_streaming() -> None:
        response = await orchestrator.process_user_message_streaming(
            session_id=session_id,
            user_id=user_id,
            message=message,
            on_text_delta=_on_text_delta,
            on_stream_end=_on_stream_end,
            progress_callback=_progress_callback,
            host_status=host_status,
        )

        # Send stream end with metadata
        end_msg = _build_message(
            MessageType.CHAT_STREAM_END,
            ChatStreamEndPayload(
                message_id=message_id,
                full_text=response.response_text,
                model_used=response.model_used,
                tokens_used={
                    "input": response.tokens_input,
                    "output": response.tokens_output,
                },
            ).model_dump(),
            session_id=session_id,
        )
        await manager.send_json(connection_id, end_msg)

    task = asyncio.create_task(_run_streaming())
    _active_streams[connection_id] = task

    try:
        await task
    except asyncio.CancelledError:
        await logger.ainfo(
            "streaming_interrupted",
            connection_id=connection_id,
            session_id=session_id,
        )
        # Cancel any pending TTS tasks
        for tts_task in tts_tasks:
            if not tts_task.done():
                tts_task.cancel()
    finally:
        _active_streams.pop(connection_id, None)


async def _send_tts_chunk(
    tts_service: "TTSService",
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

    if not submitted:
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
