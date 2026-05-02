"""WebSocket connection manager with heartbeat support."""

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import structlog
from fastapi import WebSocket
from starlette.websockets import WebSocketState

from app.core import metrics as _metrics

logger: structlog.stdlib.BoundLogger = structlog.get_logger()


class ConnectionInfo:
    """Tracks metadata for a single WebSocket connection."""

    __slots__ = ("websocket", "user_id", "session_id", "connected_at", "_heartbeat_task")

    def __init__(
        self,
        websocket: WebSocket,
        user_id: str,
        session_id: str,
    ) -> None:
        self.websocket = websocket
        self.user_id = user_id
        self.session_id = session_id
        self.connected_at = datetime.now(tz=UTC)
        self._heartbeat_task: asyncio.Task[None] | None = None

    @property
    def heartbeat_task(self) -> asyncio.Task[None] | None:
        """Return the heartbeat task for this connection."""
        return self._heartbeat_task

    @heartbeat_task.setter
    def heartbeat_task(self, task: asyncio.Task[None] | None) -> None:
        """Set the heartbeat task for this connection."""
        self._heartbeat_task = task


class ConnectionManager:
    """Manages active WebSocket connections with heartbeat support."""

    def __init__(
        self,
        heartbeat_interval: int = 30,
        heartbeat_timeout: int = 10,
        kind: str = "ios",
    ) -> None:
        """Initialise the connection manager.

        ``kind`` labels the Prometheus ``ws_connections_active`` gauge so
        a single Grafana panel can split iOS clients from bridge
        connections (T2.2). Defaults to ``"ios"`` because the historical
        constructor call sites (``api/routes/websocket.py``) are the iOS
        endpoint; the bridge-side instance in ``api/routes/agent_ws.py``
        passes ``kind="bridge"`` explicitly.
        """
        self._connections: dict[str, ConnectionInfo] = {}
        self._heartbeat_interval = heartbeat_interval
        self._heartbeat_timeout = heartbeat_timeout
        self._kind = kind

    def _generate_connection_id(self, user_id: str) -> str:
        """Generate a unique connection ID for a user (multi-device support)."""
        return f"{user_id}:{uuid4()}"

    async def connect(
        self,
        websocket: WebSocket,
        user_id: str,
        session_id: str,
    ) -> str:
        """Accept and register a new WebSocket connection.

        Returns:
            The generated connection_id.
        """
        await websocket.accept()
        connection_id = self._generate_connection_id(user_id)
        info = ConnectionInfo(
            websocket=websocket,
            user_id=user_id,
            session_id=session_id,
        )
        self._connections[connection_id] = info
        # T2.2: track active WS sessions by kind (ios|bridge).
        _metrics.ws_connections_active.labels(kind=self._kind).inc()
        await logger.ainfo(
            "websocket_connected",
            connection_id=connection_id,
            user_id=user_id,
            session_id=session_id,
            active_count=len(self._connections),
        )
        return connection_id

    async def disconnect(self, connection_id: str) -> None:
        """Remove a WebSocket connection and cancel its heartbeat."""
        info = self._connections.pop(connection_id, None)
        if info is not None:
            if info.heartbeat_task is not None and not info.heartbeat_task.done():
                info.heartbeat_task.cancel()
            # T2.2: mirror the increment in :meth:`connect` so the gauge
            # stays accurate. ``disconnect`` is the only path that removes
            # an entry from ``_connections`` (broadcast/send_to_user
            # call back into it on failure), so a double-decrement is
            # impossible.
            _metrics.ws_connections_active.labels(kind=self._kind).dec()
            await logger.ainfo(
                "websocket_disconnected",
                connection_id=connection_id,
                user_id=info.user_id,
                active_count=len(self._connections),
            )

    async def send_json(self, connection_id: str, data: dict[str, object]) -> bool:
        """Send JSON data to a specific connection.

        Returns:
            True if message was sent, False if connection not found or send failed.
        """
        info = self._connections.get(connection_id)
        if info is None:
            return False
        try:
            if info.websocket.client_state == WebSocketState.CONNECTED:
                await info.websocket.send_json(data)
                return True
        except Exception:
            await logger.awarning(
                "send_json_failed",
                connection_id=connection_id,
            )
            await self.disconnect(connection_id)
        return False

    async def broadcast_json(self, data: dict[str, object]) -> None:
        """Broadcast JSON data to all active connections."""
        failed_connections: list[str] = []
        for connection_id in list(self._connections.keys()):
            sent = await self.send_json(connection_id, data)
            if not sent:
                failed_connections.append(connection_id)
        for connection_id in failed_connections:
            await self.disconnect(connection_id)

    async def send_to_user(self, user_id: str, data: dict[str, object]) -> int:
        """Send JSON data to all connections of a specific user.

        Returns:
            Number of connections the message was sent to.
        """
        sent_count = 0
        for connection_id, info in list(self._connections.items()):
            if info.user_id == user_id and await self.send_json(connection_id, data):
                sent_count += 1
        return sent_count

    def get_connection(self, connection_id: str) -> ConnectionInfo | None:
        """Return connection info for a given connection ID."""
        return self._connections.get(connection_id)

    def get_user_connections(self, user_id: str) -> list[str]:
        """Return all connection IDs for a given user."""
        return [cid for cid, info in self._connections.items() if info.user_id == user_id]

    def get_active_user_ids(self) -> set[str]:
        """Return the set of unique ``user_id``s with at least one active connection.

        Used by global broadcast paths (e.g. T1.2 ``usage.report`` fan-out
        from a bridge) that need to deliver one message per user — not one
        per connection. Multi-device users are correctly counted once.
        """
        return {info.user_id for info in self._connections.values()}

    @property
    def active_count(self) -> int:
        """Return the number of active connections."""
        return len(self._connections)

    @property
    def heartbeat_interval(self) -> int:
        """Return the heartbeat interval in seconds."""
        return self._heartbeat_interval

    @property
    def heartbeat_timeout(self) -> int:
        """Return the heartbeat timeout in seconds."""
        return self._heartbeat_timeout

    async def start_heartbeat(self, connection_id: str) -> None:
        """Start a heartbeat task for a connection."""
        info = self._connections.get(connection_id)
        if info is None:
            return

        async def _heartbeat_loop() -> None:
            """Periodically send ping and wait for pong."""
            try:
                while connection_id in self._connections:
                    await asyncio.sleep(self._heartbeat_interval)
                    if connection_id not in self._connections:
                        break
                    conn = self._connections.get(connection_id)
                    if conn is None:
                        break
                    try:
                        ping_data: dict[str, object] = {
                            "id": str(uuid4()),
                            "type": "ping",
                            "content": {
                                "timestamp": datetime.now(tz=UTC).isoformat(),
                            },
                        }
                        if conn.websocket.client_state == WebSocketState.CONNECTED:
                            await conn.websocket.send_json(ping_data)
                            await logger.adebug(
                                "heartbeat_ping_sent",
                                connection_id=connection_id,
                            )
                    except Exception:
                        await logger.awarning(
                            "heartbeat_ping_failed",
                            connection_id=connection_id,
                        )
                        await self.disconnect(connection_id)
                        break
            except asyncio.CancelledError:
                pass

        task = asyncio.create_task(_heartbeat_loop())
        info.heartbeat_task = task
