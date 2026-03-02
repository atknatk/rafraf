"""WebSocket connection manager."""

import structlog
from fastapi import WebSocket

logger: structlog.stdlib.BoundLogger = structlog.get_logger()


class ConnectionManager:
    """Manages active WebSocket connections."""

    def __init__(self) -> None:
        self._active_connections: dict[str, WebSocket] = {}

    async def connect(self, connection_id: str, websocket: WebSocket) -> None:
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        self._active_connections[connection_id] = websocket
        await logger.ainfo(
            "websocket_connected",
            connection_id=connection_id,
            active_count=len(self._active_connections),
        )

    async def disconnect(self, connection_id: str) -> None:
        """Remove a WebSocket connection."""
        self._active_connections.pop(connection_id, None)
        await logger.ainfo(
            "websocket_disconnected",
            connection_id=connection_id,
            active_count=len(self._active_connections),
        )

    async def send_json(self, connection_id: str, data: dict[str, object]) -> None:
        """Send JSON data to a specific connection."""
        websocket = self._active_connections.get(connection_id)
        if websocket is not None:
            await websocket.send_json(data)

    async def broadcast_json(self, data: dict[str, object]) -> None:
        """Broadcast JSON data to all active connections."""
        for connection_id, websocket in self._active_connections.items():
            try:
                await websocket.send_json(data)
            except Exception:
                await logger.awarning(
                    "broadcast_send_failed",
                    connection_id=connection_id,
                )

    @property
    def active_count(self) -> int:
        """Return the number of active connections."""
        return len(self._active_connections)
