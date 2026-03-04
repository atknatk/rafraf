"""WSS baglanti yonetimi - connect, reconnect, heartbeat."""

from __future__ import annotations

import asyncio
import contextlib
import platform
import time
from typing import TYPE_CHECKING

import structlog
import websockets
from websockets.asyncio.client import ClientConnection

from agent.core.protocol import (
    ResourceMetrics,
    build_heartbeat_message,
    build_register_message,
    parse_register_ack,
    parse_server_message,
)
from agent.monitoring.metrics import get_resource_metrics

if TYPE_CHECKING:
    from agent.core.config import AgentConfig

logger = structlog.get_logger()


class ConnectionManager:
    """WSS baglanti yonetimi.

    Backend'e WebSocket ile baglanir, heartbeat gonderir,
    kopmalarda exponential backoff ile yeniden baglanir.
    """

    def __init__(self, config: AgentConfig) -> None:
        self._config = config
        self._ws: ClientConnection | None = None
        self._is_connected: bool = False
        self._reconnect_delay: float = config.reconnect_initial_delay
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._listen_task: asyncio.Task[None] | None = None
        self._start_time: float = time.monotonic()
        self._active_tasks: int = 0
        self._should_run: bool = True
        self._heartbeat_interval: int = config.heartbeat_interval

    @property
    def is_connected(self) -> bool:
        """Baglanti durumunu dondurur."""
        return self._is_connected

    @property
    def uptime_seconds(self) -> int:
        """Agent calisma suresini saniye olarak dondurur."""
        return int(time.monotonic() - self._start_time)

    def _get_os_info(self) -> str:
        """Isletim sistemi bilgisini dondurur."""
        return f"{platform.system()} {platform.release()}"

    def _calculate_backoff(self) -> float:
        """Exponential backoff hesaplar ve delay'i gunceller.

        Returns:
            Guncel bekleme suresi (saniye).
        """
        current_delay = self._reconnect_delay
        self._reconnect_delay = min(
            self._reconnect_delay * 2,
            self._config.reconnect_max_delay,
        )
        return current_delay

    def _reset_backoff(self) -> None:
        """Backoff delay'ini sifirlar."""
        self._reconnect_delay = self._config.reconnect_initial_delay

    async def _send_register(self) -> None:
        """Backend'e agent_register mesaji gonderir."""
        if self._ws is None:
            return

        message = build_register_message(
            host_id=self._config.host_id,
            capabilities=self._config.get_capabilities(),
            os_info=self._get_os_info(),
            version=self._config.version,
        )
        await self._ws.send(message)
        await logger.ainfo(
            "agent_register mesaji gonderildi",
            host_id=self._config.host_id,
        )

    async def _wait_for_register_ack(self) -> bool:
        """agent_register_ack mesajini bekler.

        Returns:
            True eger kayit onaylandi, False aksi halde.
        """
        if self._ws is None:
            return False

        try:
            raw = await asyncio.wait_for(self._ws.recv(), timeout=10.0)
            data = parse_server_message(str(raw))
            ack = parse_register_ack(data)

            if ack.registered:
                self._heartbeat_interval = ack.heartbeat_interval
                await logger.ainfo(
                    "Agent kayit onaylandi",
                    host_id=ack.host_id,
                    heartbeat_interval=ack.heartbeat_interval,
                )
                return True

            await logger.awarning(
                "Agent kayit reddedildi",
                host_id=ack.host_id,
            )
            return False

        except TimeoutError:
            await logger.awarning("agent_register_ack bekleme zamani asimi")
            return False
        except ValueError as exc:
            await logger.awarning(
                "agent_register_ack parse hatasi",
                error=str(exc),
            )
            return False

    async def _heartbeat_loop(self) -> None:
        """Periyodik heartbeat gonderme dongusu."""
        while self._is_connected and self._should_run:
            try:
                await asyncio.sleep(self._heartbeat_interval)

                if not self._is_connected or self._ws is None:
                    break

                resources: ResourceMetrics = await get_resource_metrics()
                message = build_heartbeat_message(
                    host_id=self._config.host_id,
                    status="online" if self._active_tasks == 0 else "busy",
                    uptime_seconds=self.uptime_seconds,
                    active_tasks=self._active_tasks,
                    resources=resources,
                )
                await self._ws.send(message)
                await logger.adebug(
                    "Heartbeat gonderildi",
                    uptime=self.uptime_seconds,
                )

            except websockets.exceptions.ConnectionClosed:
                await logger.awarning("Heartbeat sirasinda baglanti koptu")
                self._is_connected = False
                break
            except Exception:
                await logger.aexception("Heartbeat gonderme hatasi")
                self._is_connected = False
                break

    async def _listen_loop(self) -> None:
        """Server'dan gelen mesajlari dinler."""
        if self._ws is None:
            return

        try:
            async for raw in self._ws:
                try:
                    data = parse_server_message(str(raw))
                    await logger.ainfo(
                        "Mesaj alindi",
                        message_type=data.get("type"),
                    )
                    # Simdilik mesajlari sadece logluyoruz
                    # Komut islemleri ilerideki issue'larda eklenecek
                except ValueError as exc:
                    await logger.awarning(
                        "Mesaj parse hatasi",
                        error=str(exc),
                    )
        except websockets.exceptions.ConnectionClosed:
            await logger.awarning("Listen sirasinda baglanti koptu")
        finally:
            self._is_connected = False

    async def connect(self) -> None:
        """Backend'e WSS baglantisi kurar.

        Baglanti koparsa exponential backoff ile yeniden baglanir.
        should_run False olana kadar calisir.
        """
        while self._should_run:
            try:
                await logger.ainfo(
                    "WSS baglantisi kuruluyor",
                    url=self._config.backend_ws_url,
                    host_id=self._config.host_id,
                )

                # Backend api_key'i query parameter olarak bekliyor
                ws_url = f"{self._config.backend_ws_url}?api_key={self._config.api_key}"
                self._ws = await websockets.connect(ws_url)
                self._is_connected = True
                self._reset_backoff()

                await logger.ainfo("WSS baglantisi kuruldu")

                # Register
                await self._send_register()
                registered = await self._wait_for_register_ack()

                if not registered:
                    await self._ws.close()
                    self._is_connected = False
                    delay = self._calculate_backoff()
                    await logger.awarning(
                        "Kayit basarisiz, yeniden denenecek",
                        delay=delay,
                    )
                    await asyncio.sleep(delay)
                    continue

                # Heartbeat ve listen basla
                self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
                self._listen_task = asyncio.create_task(self._listen_loop())

                # Listen task bitene kadar bekle (baglanti kopma)
                await self._listen_task

                # Heartbeat task'i iptal et
                if self._heartbeat_task and not self._heartbeat_task.done():
                    self._heartbeat_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await self._heartbeat_task

            except (
                OSError,
                websockets.exceptions.WebSocketException,
            ):
                self._is_connected = False
                if not self._should_run:
                    break

                delay = self._calculate_backoff()
                await logger.awarning(
                    "Baglanti hatasi, yeniden denenecek",
                    delay=delay,
                )
                await asyncio.sleep(delay)

            except asyncio.CancelledError:
                await logger.ainfo("Baglanti task iptal edildi")
                break

        self._is_connected = False

    async def shutdown(self) -> None:
        """Baglantilari temiz kapatir (graceful shutdown)."""
        await logger.ainfo("Graceful shutdown baslatiliyor...")
        self._should_run = False
        self._is_connected = False

        # Heartbeat task iptal
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._heartbeat_task

        # Listen task iptal
        if self._listen_task and not self._listen_task.done():
            self._listen_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._listen_task

        # WebSocket kapat
        if self._ws is not None:
            with contextlib.suppress(Exception):
                await self._ws.close()
            self._ws = None

        await logger.ainfo("Graceful shutdown tamamlandi")
