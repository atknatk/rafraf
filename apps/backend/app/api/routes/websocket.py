"""WebSocket endpoint for iOS client connections."""

from datetime import UTC, datetime
from uuid import uuid4

import structlog
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.security import SecurityError, verify_access_token
from app.core.websocket import ConnectionManager
from app.schemas.messages import (
    ConnectionAckPayload,
    ErrorPayload,
    MessageDirection,
    MessageType,
    ProgressPayload,
)
from app.services.orchestrator_service import OrchestratorService

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

router = APIRouter()

manager = ConnectionManager(heartbeat_interval=30, heartbeat_timeout=10)


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

    # Route through AI orchestrator (transcribed text)
    await _process_with_orchestrator(
        message=content,
        connection_id=connection_id,
        session_id=session_id,
        user_id=user_id,
    )


async def _process_with_orchestrator(
    *,
    message: str,
    connection_id: str,
    session_id: str,
    user_id: str,
) -> None:
    """Process a message through the AI orchestrator and send the response.

    Sends progress updates during tool execution and the final AI response.
    """
    orchestrator = OrchestratorService()

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

    response = await orchestrator.process_user_message(
        session_id=session_id,
        user_id=user_id,
        message=message,
        progress_callback=_progress_callback,
    )

    # Send AI response to client
    response_msg = _build_message(
        MessageType.TEXT,
        {
            "text": response.response_text,
            "model_used": response.model_used,
            "tokens_used": {
                "input": response.tokens_input,
                "output": response.tokens_output,
            },
        },
        session_id=session_id,
    )
    await manager.send_json(connection_id, response_msg)
