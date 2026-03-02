"""Unit tests for WebSocket ConnectionManager."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.websockets import WebSocketState

from app.core.websocket import ConnectionInfo, ConnectionManager


class TestConnectionInfo:
    """Tests for ConnectionInfo data class."""

    def test_create_connection_info(self) -> None:
        """ConnectionInfo should store websocket, user_id, session_id."""
        ws = MagicMock()
        info = ConnectionInfo(websocket=ws, user_id="user-1", session_id="sess-1")
        assert info.websocket is ws
        assert info.user_id == "user-1"
        assert info.session_id == "sess-1"
        assert info.connected_at is not None
        assert info.heartbeat_task is None

    def test_heartbeat_task_property(self) -> None:
        """heartbeat_task should be settable and gettable."""
        ws = MagicMock()
        info = ConnectionInfo(websocket=ws, user_id="user-1", session_id="sess-1")
        mock_task = MagicMock()
        info.heartbeat_task = mock_task
        assert info.heartbeat_task is mock_task


class TestConnectionManager:
    """Tests for ConnectionManager."""

    @pytest.fixture
    def manager(self) -> ConnectionManager:
        """Create a fresh ConnectionManager."""
        return ConnectionManager(heartbeat_interval=30, heartbeat_timeout=10)

    @pytest.fixture
    def mock_websocket(self) -> MagicMock:
        """Create a mock WebSocket."""
        ws = AsyncMock()
        ws.accept = AsyncMock()
        ws.send_json = AsyncMock()
        ws.client_state = WebSocketState.CONNECTED
        return ws

    async def test_connect_accepts_websocket(
        self, manager: ConnectionManager, mock_websocket: MagicMock
    ) -> None:
        """connect() should accept the WebSocket and store the connection."""
        connection_id = await manager.connect(
            websocket=mock_websocket, user_id="user-1", session_id="sess-1"
        )
        assert connection_id.startswith("user-1:")
        assert manager.active_count == 1
        mock_websocket.accept.assert_awaited_once()

    async def test_connect_returns_unique_ids(
        self, manager: ConnectionManager
    ) -> None:
        """connect() should return unique connection IDs for same user."""
        ws1 = AsyncMock()
        ws1.accept = AsyncMock()
        ws2 = AsyncMock()
        ws2.accept = AsyncMock()
        cid1 = await manager.connect(websocket=ws1, user_id="user-1", session_id="s1")
        cid2 = await manager.connect(websocket=ws2, user_id="user-1", session_id="s2")
        assert cid1 != cid2
        assert manager.active_count == 2

    async def test_disconnect_removes_connection(
        self, manager: ConnectionManager, mock_websocket: MagicMock
    ) -> None:
        """disconnect() should remove a connection."""
        cid = await manager.connect(
            websocket=mock_websocket, user_id="user-1", session_id="sess-1"
        )
        assert manager.active_count == 1
        await manager.disconnect(cid)
        assert manager.active_count == 0

    async def test_disconnect_nonexistent_id(
        self, manager: ConnectionManager
    ) -> None:
        """disconnect() with unknown ID should not raise."""
        await manager.disconnect("nonexistent-id")
        assert manager.active_count == 0

    async def test_disconnect_cancels_heartbeat(
        self, manager: ConnectionManager, mock_websocket: MagicMock
    ) -> None:
        """disconnect() should cancel the heartbeat task if running."""
        cid = await manager.connect(
            websocket=mock_websocket, user_id="user-1", session_id="sess-1"
        )
        info = manager.get_connection(cid)
        assert info is not None
        mock_task = MagicMock()
        mock_task.done.return_value = False
        mock_task.cancel = MagicMock()
        info.heartbeat_task = mock_task
        await manager.disconnect(cid)
        mock_task.cancel.assert_called_once()

    async def test_send_json_to_connected(
        self, manager: ConnectionManager, mock_websocket: MagicMock
    ) -> None:
        """send_json() should send data to a connected WebSocket."""
        cid = await manager.connect(
            websocket=mock_websocket, user_id="user-1", session_id="sess-1"
        )
        data: dict[str, object] = {"type": "test", "content": "hello"}
        result = await manager.send_json(cid, data)
        assert result is True
        mock_websocket.send_json.assert_awaited_once_with(data)

    async def test_send_json_to_unknown_id(
        self, manager: ConnectionManager
    ) -> None:
        """send_json() should return False for unknown connection ID."""
        result = await manager.send_json("unknown", {"type": "test"})
        assert result is False

    async def test_send_json_handles_send_failure(
        self, manager: ConnectionManager, mock_websocket: MagicMock
    ) -> None:
        """send_json() should handle send errors and disconnect."""
        mock_websocket.send_json.side_effect = RuntimeError("Connection lost")
        cid = await manager.connect(
            websocket=mock_websocket, user_id="user-1", session_id="sess-1"
        )
        result = await manager.send_json(cid, {"type": "test"})
        assert result is False
        assert manager.active_count == 0

    async def test_broadcast_json(
        self, manager: ConnectionManager
    ) -> None:
        """broadcast_json() should send to all connections."""
        ws1 = AsyncMock()
        ws1.accept = AsyncMock()
        ws1.send_json = AsyncMock()
        ws1.client_state = WebSocketState.CONNECTED
        ws2 = AsyncMock()
        ws2.accept = AsyncMock()
        ws2.send_json = AsyncMock()
        ws2.client_state = WebSocketState.CONNECTED

        await manager.connect(websocket=ws1, user_id="user-1", session_id="s1")
        await manager.connect(websocket=ws2, user_id="user-2", session_id="s2")

        data: dict[str, object] = {"type": "broadcast", "content": "hello all"}
        await manager.broadcast_json(data)
        ws1.send_json.assert_awaited_once_with(data)
        ws2.send_json.assert_awaited_once_with(data)

    async def test_send_to_user(
        self, manager: ConnectionManager
    ) -> None:
        """send_to_user() should send to all connections of a user."""
        ws1 = AsyncMock()
        ws1.accept = AsyncMock()
        ws1.send_json = AsyncMock()
        ws1.client_state = WebSocketState.CONNECTED
        ws2 = AsyncMock()
        ws2.accept = AsyncMock()
        ws2.send_json = AsyncMock()
        ws2.client_state = WebSocketState.CONNECTED
        ws3 = AsyncMock()
        ws3.accept = AsyncMock()
        ws3.send_json = AsyncMock()
        ws3.client_state = WebSocketState.CONNECTED

        await manager.connect(websocket=ws1, user_id="user-1", session_id="s1")
        await manager.connect(websocket=ws2, user_id="user-1", session_id="s2")
        await manager.connect(websocket=ws3, user_id="user-2", session_id="s3")

        data: dict[str, object] = {"type": "test", "content": "for user-1"}
        count = await manager.send_to_user("user-1", data)
        assert count == 2
        ws1.send_json.assert_awaited_once_with(data)
        ws2.send_json.assert_awaited_once_with(data)
        ws3.send_json.assert_not_awaited()

    async def test_get_connection(
        self, manager: ConnectionManager, mock_websocket: MagicMock
    ) -> None:
        """get_connection() should return ConnectionInfo."""
        cid = await manager.connect(
            websocket=mock_websocket, user_id="user-1", session_id="sess-1"
        )
        info = manager.get_connection(cid)
        assert info is not None
        assert info.user_id == "user-1"

    async def test_get_connection_unknown(
        self, manager: ConnectionManager
    ) -> None:
        """get_connection() should return None for unknown ID."""
        assert manager.get_connection("unknown") is None

    async def test_get_user_connections(
        self, manager: ConnectionManager
    ) -> None:
        """get_user_connections() should return all IDs for a user."""
        ws1 = AsyncMock()
        ws1.accept = AsyncMock()
        ws2 = AsyncMock()
        ws2.accept = AsyncMock()

        cid1 = await manager.connect(websocket=ws1, user_id="user-1", session_id="s1")
        cid2 = await manager.connect(websocket=ws2, user_id="user-1", session_id="s2")

        connections = manager.get_user_connections("user-1")
        assert set(connections) == {cid1, cid2}

    async def test_get_user_connections_empty(
        self, manager: ConnectionManager
    ) -> None:
        """get_user_connections() should return empty list for unknown user."""
        assert manager.get_user_connections("unknown") == []

    def test_active_count_empty(self, manager: ConnectionManager) -> None:
        """active_count should be 0 initially."""
        assert manager.active_count == 0

    def test_heartbeat_interval_property(self, manager: ConnectionManager) -> None:
        """heartbeat_interval property should return configured value."""
        assert manager.heartbeat_interval == 30

    def test_heartbeat_timeout_property(self, manager: ConnectionManager) -> None:
        """heartbeat_timeout property should return configured value."""
        assert manager.heartbeat_timeout == 10
