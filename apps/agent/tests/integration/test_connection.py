"""Integration tests for WSS connection, heartbeat, and reconnect."""

from __future__ import annotations

import asyncio
import json

import websockets
from websockets.asyncio.server import ServerConnection

from agent.core.config import AgentConfig
from agent.core.connection import ConnectionManager


class TestWSConnection:
    """WSS baglanti integration testleri.

    Gercek WebSocket server olusturarak test eder.
    """

    async def _create_test_server(
        self,
        handler: object,
    ) -> tuple[websockets.asyncio.server.Server, int]:
        """Test WebSocket server olusturur."""
        server = await websockets.serve(
            handler,  # type: ignore[arg-type]
            "localhost",
            0,
        )
        port = server.sockets[0].getsockname()[1]
        return server, port

    def _make_config(self, port: int, heartbeat_interval: int = 60) -> AgentConfig:
        """Test config olusturur."""
        return AgentConfig(
            host_id="integration-test",
            api_key="test-key",
            backend_ws_url=f"ws://localhost:{port}",
            heartbeat_interval=heartbeat_interval,
            reconnect_initial_delay=0.1,
            reconnect_max_delay=1.0,
            version="0.1.0-test",
        )

    async def test_connect_and_register(self) -> None:
        """Agent basarili sekilde baglanir ve register mesaji gonderir."""
        received_messages: list[dict[str, object]] = []

        async def handler(ws: ServerConnection) -> None:
            msg = await ws.recv()
            data = json.loads(str(msg))
            received_messages.append(data)

            # Register ack gonder
            ack = json.dumps(
                {
                    "type": "agent_register_ack",
                    "content": {
                        "host_id": "integration-test",
                        "registered": True,
                        "server_time": "2026-03-02T10:00:00Z",
                        "heartbeat_interval": 60,
                    },
                }
            )
            await ws.send(ack)
            await asyncio.sleep(0.5)
            await ws.close()

        server, port = await self._create_test_server(handler)
        config = self._make_config(port)
        cm = ConnectionManager(config)

        connect_task = asyncio.create_task(cm.connect())
        await asyncio.sleep(1.0)
        await cm.shutdown()
        connect_task.cancel()
        try:
            await connect_task
        except asyncio.CancelledError:
            pass

        server.close()
        await server.wait_closed()

        assert len(received_messages) >= 1
        assert received_messages[0]["type"] == "agent_register"
        assert received_messages[0]["content"]["host_id"] == "integration-test"

    async def test_heartbeat_sent(self) -> None:
        """Agent heartbeat mesajlari gonderir."""
        received_messages: list[dict[str, object]] = []

        async def handler(ws: ServerConnection) -> None:
            msg = await ws.recv()
            data = json.loads(str(msg))
            received_messages.append(data)

            # Register ack gonder - heartbeat_interval=1 (server tarafli override)
            ack = json.dumps(
                {
                    "type": "agent_register_ack",
                    "content": {
                        "host_id": "integration-test",
                        "registered": True,
                        "server_time": "2026-03-02T10:00:00Z",
                        "heartbeat_interval": 1,
                    },
                }
            )
            await ws.send(ack)

            # Heartbeat mesajlarini al
            try:
                while True:
                    msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    data = json.loads(str(msg))
                    received_messages.append(data)
            except (TimeoutError, websockets.exceptions.ConnectionClosed):
                pass

        server, port = await self._create_test_server(handler)
        config = self._make_config(port, heartbeat_interval=5)
        cm = ConnectionManager(config)

        connect_task = asyncio.create_task(cm.connect())
        # heartbeat_interval server'dan 1s olarak set edilecek, 3.5s yeterli
        await asyncio.sleep(3.5)
        await cm.shutdown()
        connect_task.cancel()
        try:
            await connect_task
        except asyncio.CancelledError:
            pass

        server.close()
        await server.wait_closed()

        heartbeat_messages = [m for m in received_messages if m["type"] == "agent_heartbeat"]
        assert len(heartbeat_messages) >= 1

        hb = heartbeat_messages[0]
        assert hb["content"]["host_id"] == "integration-test"
        assert hb["content"]["status"] in ("online", "busy")
        assert "resources" in hb["content"]

    async def test_reconnect_on_server_close(self) -> None:
        """Server baglantiyi kapatinca agent yeniden baglanir."""
        connection_count = 0

        async def handler(ws: ServerConnection) -> None:
            nonlocal connection_count
            connection_count += 1

            await ws.recv()
            ack = json.dumps(
                {
                    "type": "agent_register_ack",
                    "content": {
                        "host_id": "integration-test",
                        "registered": True,
                        "server_time": "2026-03-02T10:00:00Z",
                        "heartbeat_interval": 60,
                    },
                }
            )
            await ws.send(ack)

            if connection_count == 1:
                await asyncio.sleep(0.2)
                await ws.close()
            else:
                await asyncio.sleep(2.0)

        server, port = await self._create_test_server(handler)
        config = self._make_config(port)
        cm = ConnectionManager(config)

        connect_task = asyncio.create_task(cm.connect())
        await asyncio.sleep(2.0)
        await cm.shutdown()
        connect_task.cancel()
        try:
            await connect_task
        except asyncio.CancelledError:
            pass

        server.close()
        await server.wait_closed()

        assert connection_count >= 2

    async def test_graceful_shutdown(self) -> None:
        """Graceful shutdown temiz bir sekilde kapanir."""

        async def handler(ws: ServerConnection) -> None:
            await ws.recv()
            ack = json.dumps(
                {
                    "type": "agent_register_ack",
                    "content": {
                        "host_id": "integration-test",
                        "registered": True,
                        "server_time": "2026-03-02T10:00:00Z",
                        "heartbeat_interval": 60,
                    },
                }
            )
            await ws.send(ack)
            try:
                await asyncio.sleep(10.0)
            except asyncio.CancelledError:
                pass

        server, port = await self._create_test_server(handler)
        config = self._make_config(port)
        cm = ConnectionManager(config)

        connect_task = asyncio.create_task(cm.connect())
        await asyncio.sleep(0.5)

        assert cm.is_connected is True

        await cm.shutdown()
        assert cm.is_connected is False

        connect_task.cancel()
        try:
            await connect_task
        except asyncio.CancelledError:
            pass

        server.close()
        await server.wait_closed()

    async def test_register_rejection_triggers_reconnect(self) -> None:
        """Kayit reddedildiginde yeniden baglanma denemesi yapilir."""
        attempt_count = 0

        async def handler(ws: ServerConnection) -> None:
            nonlocal attempt_count
            attempt_count += 1
            await ws.recv()

            registered = attempt_count >= 2

            ack = json.dumps(
                {
                    "type": "agent_register_ack",
                    "content": {
                        "host_id": "integration-test",
                        "registered": registered,
                        "server_time": "2026-03-02T10:00:00Z",
                        "heartbeat_interval": 60,
                    },
                }
            )
            await ws.send(ack)

            if registered:
                try:
                    await asyncio.sleep(2.0)
                except asyncio.CancelledError:
                    pass

        server, port = await self._create_test_server(handler)
        config = self._make_config(port)
        cm = ConnectionManager(config)

        connect_task = asyncio.create_task(cm.connect())
        await asyncio.sleep(2.0)
        await cm.shutdown()
        connect_task.cancel()
        try:
            await connect_task
        except asyncio.CancelledError:
            pass

        server.close()
        await server.wait_closed()

        assert attempt_count >= 2
