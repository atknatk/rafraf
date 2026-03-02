"""Integration tests for connection error scenarios."""

from __future__ import annotations

import asyncio
import json

import websockets
from websockets.asyncio.server import ServerConnection

from agent.core.config import AgentConfig
from agent.core.connection import ConnectionManager


class TestConnectionErrors:
    """Baglanti hata senaryolari testleri."""

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

    def _make_config(self, port: int) -> AgentConfig:
        """Test config olusturur."""
        return AgentConfig(
            host_id="error-test",
            api_key="test-key",
            backend_ws_url=f"ws://localhost:{port}",
            heartbeat_interval=5,
            reconnect_initial_delay=0.1,
            reconnect_max_delay=1.0,
            version="0.1.0-test",
        )

    async def test_connect_to_nonexistent_server(self) -> None:
        """Var olmayan server'a baglanma denemesi reconnect tetikler."""
        config = AgentConfig(
            host_id="error-test",
            api_key="test-key",
            backend_ws_url="ws://localhost:19999",
            heartbeat_interval=5,
            reconnect_initial_delay=0.1,
            reconnect_max_delay=1.0,
            version="0.1.0-test",
        )
        cm = ConnectionManager(config)

        connect_task = asyncio.create_task(cm.connect())
        await asyncio.sleep(0.5)

        assert cm.is_connected is False

        await cm.shutdown()
        connect_task.cancel()
        try:
            await connect_task
        except asyncio.CancelledError:
            pass

    async def test_server_sends_invalid_register_ack(self) -> None:
        """Server gecersiz register ack gonderdiyse reconnect yapilir."""
        attempt_count = 0

        async def handler(ws: ServerConnection) -> None:
            nonlocal attempt_count
            attempt_count += 1
            await ws.recv()

            if attempt_count == 1:
                # Gecersiz ack gonder (type yanlis)
                await ws.send(json.dumps({"type": "unknown_type", "content": {}}))
                await asyncio.sleep(0.5)
                await ws.close()
            else:
                ack = json.dumps(
                    {
                        "type": "agent_register_ack",
                        "content": {
                            "host_id": "error-test",
                            "registered": True,
                            "server_time": "2026-03-02T10:00:00Z",
                            "heartbeat_interval": 60,
                        },
                    }
                )
                await ws.send(ack)
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

        # parse hatasi sonrasi yeniden baglanti denemesi
        assert attempt_count >= 2

    async def test_shutdown_without_connection(self) -> None:
        """Baglanti kurulmadan shutdown cagirmak hata vermez."""
        config = AgentConfig(
            host_id="error-test",
            api_key="test-key",
            backend_ws_url="ws://localhost:19999",
            heartbeat_interval=5,
            reconnect_initial_delay=0.1,
            reconnect_max_delay=1.0,
            version="0.1.0-test",
        )
        cm = ConnectionManager(config)
        # Hata vermeden shutdown olabilmeli
        await cm.shutdown()
        assert cm.is_connected is False

    async def test_send_register_with_no_ws(self) -> None:
        """ws None iken _send_register cagirmak hata vermez."""
        config = AgentConfig(
            host_id="error-test",
            api_key="test-key",
            backend_ws_url="ws://localhost:19999",
            heartbeat_interval=5,
            reconnect_initial_delay=0.1,
            reconnect_max_delay=1.0,
            version="0.1.0-test",
        )
        cm = ConnectionManager(config)
        # ws None - hata vermeden donmeli
        await cm._send_register()

    async def test_wait_for_register_ack_with_no_ws(self) -> None:
        """ws None iken _wait_for_register_ack False dondurur."""
        config = AgentConfig(
            host_id="error-test",
            api_key="test-key",
            backend_ws_url="ws://localhost:19999",
            heartbeat_interval=5,
            reconnect_initial_delay=0.1,
            reconnect_max_delay=1.0,
            version="0.1.0-test",
        )
        cm = ConnectionManager(config)
        result = await cm._wait_for_register_ack()
        assert result is False

    async def test_listen_loop_with_no_ws(self) -> None:
        """ws None iken _listen_loop hata vermez."""
        config = AgentConfig(
            host_id="error-test",
            api_key="test-key",
            backend_ws_url="ws://localhost:19999",
            heartbeat_interval=5,
            reconnect_initial_delay=0.1,
            reconnect_max_delay=1.0,
            version="0.1.0-test",
        )
        cm = ConnectionManager(config)
        # ws None - hemen donmeli
        await cm._listen_loop()

    async def test_server_sends_invalid_json_during_listen(self) -> None:
        """Listen sirasinda gecersiz JSON mesaj gonderilirse hata loglanir."""

        async def handler(ws: ServerConnection) -> None:
            await ws.recv()
            ack = json.dumps(
                {
                    "type": "agent_register_ack",
                    "content": {
                        "host_id": "error-test",
                        "registered": True,
                        "server_time": "2026-03-02T10:00:00Z",
                        "heartbeat_interval": 60,
                    },
                }
            )
            await ws.send(ack)
            # Gecersiz JSON gonder
            await ws.send("not-valid-json{}")
            await asyncio.sleep(0.5)
            await ws.close()

        server, port = await self._create_test_server(handler)
        config = self._make_config(port)
        cm = ConnectionManager(config)

        connect_task = asyncio.create_task(cm.connect())
        await asyncio.sleep(1.5)
        await cm.shutdown()
        connect_task.cancel()
        try:
            await connect_task
        except asyncio.CancelledError:
            pass

        server.close()
        await server.wait_closed()

    async def test_register_ack_timeout(self) -> None:
        """Register ack mesaji gelmezse timeout olur."""

        async def handler(ws: ServerConnection) -> None:
            await ws.recv()
            # Ack gondermeden bekle
            try:
                await asyncio.sleep(30.0)
            except asyncio.CancelledError:
                pass

        server, port = await self._create_test_server(handler)
        config = self._make_config(port)
        cm = ConnectionManager(config)

        connect_task = asyncio.create_task(cm.connect())
        # 10s ack timeout + reconnect delay
        await asyncio.sleep(12.0)
        await cm.shutdown()
        connect_task.cancel()
        try:
            await connect_task
        except asyncio.CancelledError:
            pass

        server.close()
        await server.wait_closed()
