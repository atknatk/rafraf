"""Bridge registry and health monitoring service.

Manages bridge registration, heartbeat tracking, and stale-bridge detection.
Uses an in-memory store for fast access (DB persistence happens via
``BridgeRepository`` as a best-effort dual-write).

Replaces the legacy ``AgentRegistryService`` as part of the V1 production
pivot (docs/10 §6.1.1, T1.3). The Python "host agent" daemon has been
archived (``apps/_archive/agent``) and superseded by the Go bridge in
``apps/rafraf-bridge/``.

T1.1 additions:
    * :meth:`send_to_bridge` — fire-and-forget RPC envelope dispatch.
    * :meth:`stream_events` — correlated AsyncIterator for the events the
      bridge emits in response to a particular RPC, keyed by
      ``correlation_id`` (= ``rpc_id``).
    * :meth:`dispatch_event` — public sink the WS endpoint
      (``agent_ws.py``) calls for every inbound bridge event so the
      runner can consume it via :meth:`stream_events`.
"""

import asyncio
import contextlib
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from app.core.websocket import ConnectionManager

from app.schemas.agent import (
    AgentCapability,
    AgentDetailResponse,
    AgentHeartbeatPayload,
    AgentListResponse,
    AgentRegisterPayload,
    AgentStatus,
    AgentSummary,
    ClaudeProcessInfo,
    ResourceInfo,
)

logger: structlog.stdlib.BoundLogger = structlog.get_logger()


class _BridgeRecord:
    """Internal mutable record for a registered bridge."""

    __slots__ = (
        "host_id",
        "status",
        "capabilities",
        "os_info",
        "version",
        "registered_at",
        "last_heartbeat_at",
        "uptime_seconds",
        "active_tasks",
        "resources",
        "metadata",
        "connection_id",
        "claude_processes",
    )

    def __init__(
        self,
        host_id: str,
        capabilities: list[AgentCapability],
        os_info: str,
        version: str,
        connection_id: str,
    ) -> None:
        self.host_id = host_id
        self.status: AgentStatus = AgentStatus.ONLINE
        self.capabilities = capabilities
        self.os_info = os_info
        self.version = version
        self.registered_at = datetime.now(tz=UTC)
        self.last_heartbeat_at: datetime | None = datetime.now(tz=UTC)
        self.uptime_seconds: int | None = None
        self.active_tasks: int | None = None
        self.resources: ResourceInfo | None = None
        self.metadata: dict[str, object] = {}
        self.connection_id = connection_id
        self.claude_processes: list[ClaudeProcessInfo] = []


class BridgeRegistryService:
    """Singleton-style service that manages the in-memory bridge registry.

    Thread-safety is ensured by asyncio's single-threaded event loop.
    """

    def __init__(
        self,
        heartbeat_timeout_seconds: int = 90,
        stale_check_interval_seconds: int = 30,
        ios_manager: "ConnectionManager | None" = None,
        agent_manager: "ConnectionManager | None" = None,
    ) -> None:
        self._bridges: dict[str, _BridgeRecord] = {}
        self._heartbeat_timeout = heartbeat_timeout_seconds
        self._stale_check_interval = stale_check_interval_seconds
        self._stale_task: asyncio.Task[None] | None = None
        self._ios_manager: ConnectionManager | None = ios_manager
        # ``agent_manager`` (the bridge-side ConnectionManager) is injected
        # lazily by ``agent_ws.py`` once both modules are imported. It owns
        # the actual WebSocket sending; the registry just looks up which
        # connection to use.
        self._agent_manager: ConnectionManager | None = agent_manager
        # Per-bridge, per-correlation-id event subscribers. Each waiter
        # receives events whose ``correlation_id`` matches the rpc_id it
        # registered under; the queue is drained until either the runner
        # cancels the iterator or a terminal event is observed.
        self._event_subscribers: dict[
            tuple[str, str], asyncio.Queue[dict[str, object]]
        ] = {}

    # ------------------------------------------------------------------
    # Backwards-compatible accessor for tests / legacy call sites.
    # ------------------------------------------------------------------

    @property
    def _agents(self) -> dict[str, "_BridgeRecord"]:
        """Alias for ``_bridges`` kept for the few tests that still call it.

        Pre-T1.3 tests (and a couple of integration fixtures) reach into the
        registry's private store via ``service._agents``. Renaming the attribute
        outright would break them; the property keeps both names pointing at
        the same dict so test refactoring can land incrementally.
        """
        return self._bridges

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start_stale_checker(self) -> None:
        """Start the background task that marks stale bridges as offline."""
        if self._stale_task is None or self._stale_task.done():
            self._stale_task = asyncio.create_task(self._stale_check_loop())
            await logger.ainfo("bridge_stale_checker_started")

    async def stop_stale_checker(self) -> None:
        """Cancel the background stale-check task."""
        if self._stale_task is not None and not self._stale_task.done():
            self._stale_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._stale_task
            await logger.ainfo("bridge_stale_checker_stopped")

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    async def register_agent(
        self,
        payload: AgentRegisterPayload,
        connection_id: str,
    ) -> bool:
        """Register or re-register a bridge.

        Returns True if newly registered, False if updated.
        Dual-write: updates both in-memory and DB.
        """
        existing = self._bridges.get(payload.host_id)
        is_new = existing is None

        record = _BridgeRecord(
            host_id=payload.host_id,
            capabilities=list(payload.capabilities),
            os_info=payload.os_info,
            version=payload.version,
            connection_id=connection_id,
        )

        self._bridges[payload.host_id] = record

        # Persist to DB (best-effort)
        try:
            from app.core.database import async_session_factory
            from app.repositories.bridge_repo import BridgeRepository

            async with async_session_factory() as db:
                repo = BridgeRepository(db)
                await repo.upsert_from_heartbeat(
                    host_id=payload.host_id,
                    status="online",
                    capabilities=[c.value for c in payload.capabilities],
                    agent_version=payload.version,
                    connection_id=connection_id,
                )
                await db.commit()
        except Exception:
            await logger.awarning("bridge_db_persist_failed", host_id=payload.host_id)

        await logger.ainfo(
            "bridge_registered",
            host_id=payload.host_id,
            is_new=is_new,
            capabilities=[c.value for c in payload.capabilities],
        )

        # Proactive broadcast to iOS clients
        if self._ios_manager:
            await self._ios_manager.broadcast_json(
                {
                    "type": "agent_status_change",
                    "host_id": payload.host_id,
                    "status": "online",
                    "is_new": is_new,
                }
            )

        return is_new

    # ------------------------------------------------------------------
    # Heartbeat
    # ------------------------------------------------------------------

    async def process_heartbeat(self, payload: AgentHeartbeatPayload) -> bool:
        """Update bridge state from a heartbeat message.

        Returns True if the bridge was found, False otherwise.
        Dual-write: updates both in-memory and DB.
        """
        record = self._bridges.get(payload.host_id)
        if record is None:
            await logger.awarning(
                "heartbeat_unknown_bridge",
                host_id=payload.host_id,
            )
            return False

        record.last_heartbeat_at = datetime.now(tz=UTC)
        record.status = payload.status
        record.uptime_seconds = payload.uptime_seconds
        record.active_tasks = payload.active_tasks
        record.resources = payload.resources
        record.claude_processes = list(payload.claude_processes)

        # Persist to DB (best-effort)
        try:
            from app.core.database import async_session_factory
            from app.repositories.bridge_repo import BridgeRepository

            resources_dict: dict[str, object] | None = None
            if payload.resources is not None:
                resources_dict = (
                    payload.resources.model_dump()
                    if hasattr(payload.resources, "model_dump")
                    else {"raw": str(payload.resources)}
                )
            async with async_session_factory() as db:
                repo = BridgeRepository(db)
                await repo.upsert_from_heartbeat(
                    host_id=payload.host_id,
                    status=payload.status.value,
                    last_resources=resources_dict,
                )
                await db.commit()
        except Exception:
            await logger.awarning("bridge_heartbeat_db_failed", host_id=payload.host_id)

        await logger.adebug(
            "bridge_heartbeat_processed",
            host_id=payload.host_id,
            status=payload.status.value,
        )
        return True

    async def update_resources(
        self,
        host_id: str,
        resources: dict[str, float],
    ) -> bool:
        """Update bridge resource metrics from a resource_report message.

        Returns True if the bridge was found, False otherwise.
        """
        record = self._bridges.get(host_id)
        if record is None:
            return False

        record.resources = ResourceInfo(
            cpu_usage_percent=resources.get("cpu_usage_percent", 0.0),
            memory_usage_percent=resources.get("memory_usage_percent", 0.0),
            disk_usage_percent=resources.get("disk_usage_percent", 0.0),
            disk_free_gb=resources.get("disk_free_gb", 0.0),
        )
        return True

    # ------------------------------------------------------------------
    # Disconnection
    # ------------------------------------------------------------------

    async def mark_disconnected(self, host_id: str) -> None:
        """Mark a bridge as offline upon WebSocket disconnect."""
        record = self._bridges.get(host_id)
        if record is not None:
            record.status = AgentStatus.OFFLINE
            # Persist to DB (best-effort)
            try:
                from app.core.database import async_session_factory
                from app.repositories.bridge_repo import BridgeRepository

                async with async_session_factory() as db:
                    repo = BridgeRepository(db)
                    await repo.mark_offline(host_id)
                    await db.commit()
            except Exception:
                await logger.awarning("bridge_disconnect_db_failed", host_id=host_id)
            await logger.ainfo("bridge_disconnected", host_id=host_id)

    async def unregister_by_connection(self, connection_id: str) -> str | None:
        """Find the bridge associated with a connection and mark it offline.

        Returns the host_id if found, None otherwise.
        """
        for record in self._bridges.values():
            if record.connection_id == connection_id:
                record.status = AgentStatus.OFFLINE
                await logger.ainfo(
                    "bridge_disconnected_by_connection",
                    host_id=record.host_id,
                    connection_id=connection_id,
                )
                return record.host_id
        return None

    # ------------------------------------------------------------------
    # Bridge RPC (T1.1) — outbound envelopes + correlated event streams.
    # ------------------------------------------------------------------

    def set_agent_manager(self, manager: "ConnectionManager") -> None:
        """Inject the bridge-side ConnectionManager.

        Called once by ``agent_ws.py`` during application startup. Kept
        as a setter (rather than a constructor arg) so the singleton at
        the bottom of this module stays importable from anywhere without
        triggering the import cycle through ``agent_ws``.
        """
        self._agent_manager = manager

    async def send_to_bridge(
        self,
        host_id: str,
        envelope: dict[str, object],
    ) -> bool:
        """Send a single RPC envelope to the bridge identified by ``host_id``.

        Returns ``True`` on a successful send, ``False`` when the bridge
        is offline, has no connection, or the manager isn't wired yet.
        """
        if self._agent_manager is None:
            await logger.awarning(
                "bridge_send_no_manager",
                host_id=host_id,
                envelope_type=envelope.get("type"),
            )
            return False
        connection_id = self.get_connection_id(host_id)
        if connection_id is None:
            await logger.awarning(
                "bridge_send_no_connection",
                host_id=host_id,
                envelope_type=envelope.get("type"),
            )
            return False
        sent: bool = await self._agent_manager.send_json(connection_id, envelope)
        return sent

    def register_subscriber(
        self,
        *,
        bridge_id: str,
        rpc_id: str,
    ) -> "asyncio.Queue[dict[str, object]]":
        """Synchronously create + register an event queue for an RPC.

        Folds in T1.1 reviewer H1: ``stream_events`` is an async generator
        whose body doesn't execute until the consumer pulls the first item,
        so the registration step has to happen *before* the bridge gets the
        envelope — otherwise an early-arriving event is dropped at
        :meth:`dispatch_event` and the runner deadlocks waiting for it.

        Callers MUST pair this with :meth:`stream_events` (which consumes
        the queue) and either let the iterator finish naturally or invoke
        :meth:`unregister_subscriber` if the RPC fails before the loop
        starts (e.g. send-to-bridge returns False).
        """
        key = (bridge_id, rpc_id)
        queue: asyncio.Queue[dict[str, object]] = asyncio.Queue()
        prev = self._event_subscribers.get(key)
        if prev is not None:
            # RPC ids are uuid4 hex; collisions are vanishingly unlikely
            # but keep the guard so a pathological test can't leak queues.
            logger.warning(
                "bridge_stream_subscriber_overwritten",
                host_id=bridge_id,
                rpc_id=rpc_id,
            )
        self._event_subscribers[key] = queue
        return queue

    def unregister_subscriber(
        self,
        *,
        bridge_id: str,
        rpc_id: str,
    ) -> None:
        """Drop a previously registered subscriber, if still present.

        Used by :class:`ClaudeCodeRunner` when a registration succeeds but
        the subsequent send-to-bridge fails — without this clean-up the
        queue would leak until process exit.
        """
        self._event_subscribers.pop((bridge_id, rpc_id), None)

    async def stream_events(
        self,
        *,
        rpc_id: str,
        bridge_id: str | None = None,
        queue: "asyncio.Queue[dict[str, object]] | None" = None,
    ) -> AsyncGenerator[dict[str, object], None]:
        """Yield bridge events whose ``correlation_id`` matches ``rpc_id``.

        Two call patterns:

        * **Pre-registered (preferred)** — caller obtains a queue via
          :meth:`register_subscriber` BEFORE sending the RPC envelope, then
          passes it here. Eliminates the race window where bridge events
          arrive faster than the consumer enters the ``async for`` loop.
        * **Lazy (legacy)** — caller skips ``queue`` and lets this method
          register on entry. Retained for tests that don't care about the
          race window. Requires ``bridge_id`` to be supplied.

        Iteration stops once a terminal event (``event.session.result`` or
        ``event.bridge.auth_expired``) is observed. The runner can also
        break out early — the queue is unregistered in either case.

        The implementation uses a single per-(bridge, rpc) queue; this is
        sufficient because exactly one runner subscribes per RPC.
        """
        if queue is None:
            if bridge_id is None:
                raise ValueError(
                    "stream_events requires either a pre-registered queue "
                    "or a bridge_id to register lazily"
                )
            queue = self.register_subscriber(bridge_id=bridge_id, rpc_id=rpc_id)
            key: tuple[str, str] | None = (bridge_id, rpc_id)
        else:
            # Find the key the caller registered under so we can pop the
            # right entry on cleanup. We trust the caller to pass the
            # same queue they got from register_subscriber; if the queue
            # isn't in the map (e.g. test mock), cleanup is a no-op.
            key = next(
                (k for k, q in self._event_subscribers.items() if q is queue),
                None,
            )
        terminal_types = {
            "event.session.result",
            "event.bridge.auth_expired",
        }
        try:
            while True:
                event = await queue.get()
                yield event
                if str(event.get("type")) in terminal_types:
                    break
        finally:
            # Pop only if the queue we yield via is still the registered
            # subscriber — defensive against the rare overwrite path.
            if key is not None and self._event_subscribers.get(key) is queue:
                self._event_subscribers.pop(key, None)

    async def dispatch_event(self, event: dict[str, object]) -> None:
        """Route an incoming bridge event to its correlated subscriber.

        Called by ``agent_ws.py`` for every envelope received on a bridge
        WebSocket. Events without a ``correlation_id`` (broadcasts such
        as ``event.bridge.alive``) are intentionally dropped — the
        runner is the only consumer for now; broadcast handling can be
        layered in later via a fan-out subscriber map.
        """
        correlation_id = event.get("correlation_id")
        if not isinstance(correlation_id, str) or not correlation_id:
            await logger.adebug(
                "bridge_event_no_correlation",
                event_type=event.get("type"),
            )
            return
        # The dispatcher accepts events from any bridge — match by
        # rpc_id alone, then narrow by host_id if multiple subscribers
        # collide on the same id (extremely unlikely with uuid4).
        for (host_id, rpc_id), queue in list(self._event_subscribers.items()):
            if rpc_id == correlation_id:
                await queue.put(event)
                await logger.adebug(
                    "bridge_event_dispatched",
                    host_id=host_id,
                    rpc_id=rpc_id,
                    event_type=event.get("type"),
                )
                return

        await logger.adebug(
            "bridge_event_no_subscriber",
            rpc_id=correlation_id,
            event_type=event.get("type"),
        )

    # ------------------------------------------------------------------
    # Connection lookup (for task dispatch)
    # ------------------------------------------------------------------

    def get_connection_id(self, host_id: str) -> str | None:
        """Return the WebSocket connection_id for a given bridge.

        Returns None if the bridge is not found or is offline.
        """
        record = self._bridges.get(host_id)
        if record is None or record.status == AgentStatus.OFFLINE:
            return None
        return record.connection_id

    async def get_agents_with_capability(
        self,
        capability: AgentCapability,
    ) -> list[AgentSummary]:
        """Return online/busy bridges that have the specified capability."""
        result: list[AgentSummary] = []
        for record in self._bridges.values():
            if record.status == AgentStatus.OFFLINE:
                continue
            if capability in record.capabilities:
                result.append(self._to_summary(record))
        return result

    def find_online_agent_with_capability(self, capability: str) -> str | None:
        """Return host_id of an online bridge with the specified capability string.

        Convenience wrapper for external callers that pass capability as string.
        Returns the least-busy matching bridge, or None.
        """
        try:
            cap = AgentCapability(capability)
        except ValueError:
            return None
        return self.get_least_busy_online(cap)

    def get_least_busy_online(
        self,
        capability: AgentCapability | None = None,
    ) -> str | None:
        """Return host_id of the least busy online bridge.

        Optionally filters by capability. Returns None if no bridge matches.
        """
        best_host: str | None = None
        best_tasks: int = 999_999
        for record in self._bridges.values():
            if record.status == AgentStatus.OFFLINE:
                continue
            if capability is not None and capability not in record.capabilities:
                continue
            tasks = record.active_tasks or 0
            if tasks < best_tasks:
                best_tasks = tasks
                best_host = record.host_id
        return best_host

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    async def list_agents(self, status_filter: AgentStatus | None = None) -> AgentListResponse:
        """Return a summary of all registered bridges."""
        agents: list[AgentSummary] = []
        online_count = 0
        for record in self._bridges.values():
            if record.status == AgentStatus.ONLINE or record.status == AgentStatus.BUSY:
                online_count += 1
            if status_filter is not None and record.status != status_filter:
                continue
            agents.append(self._to_summary(record))

        return AgentListResponse(
            agents=agents,
            total=len(agents),
            online_count=online_count,
        )

    async def get_agent(self, host_id: str) -> AgentDetailResponse | None:
        """Return detail for a single bridge, or None if not found."""
        record = self._bridges.get(host_id)
        if record is None:
            return None
        return self._to_detail(record)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _stale_check_loop(self) -> None:
        """Periodically mark bridges that missed heartbeats as offline."""
        try:
            while True:
                await asyncio.sleep(self._stale_check_interval)
                now = datetime.now(tz=UTC)
                for record in self._bridges.values():
                    if record.status == AgentStatus.OFFLINE:
                        continue
                    if record.last_heartbeat_at is None:
                        continue
                    elapsed = (now - record.last_heartbeat_at).total_seconds()
                    if elapsed > self._heartbeat_timeout:
                        await logger.awarning(
                            "bridge_stale_detected",
                            host_id=record.host_id,
                            elapsed_seconds=elapsed,
                        )
                        record.status = AgentStatus.OFFLINE
                        if self._ios_manager:
                            await self._ios_manager.broadcast_json(
                                {
                                    "type": "agent_status_change",
                                    "host_id": record.host_id,
                                    "status": "offline",
                                    "reason": "heartbeat_timeout",
                                }
                            )
        except asyncio.CancelledError:
            pass

    @staticmethod
    def _to_summary(record: _BridgeRecord) -> AgentSummary:
        return AgentSummary(
            host_id=record.host_id,
            status=record.status,
            capabilities=list(record.capabilities),
            last_heartbeat_at=(
                record.last_heartbeat_at.isoformat() if record.last_heartbeat_at else None
            ),
            os_info=record.os_info,
            uptime_seconds=record.uptime_seconds,
            active_tasks=record.active_tasks,
            resources=record.resources,
        )

    def list_agents_sync(self) -> list[dict[str, object]]:
        """Return a lightweight list of all bridges as dicts (non-async, for aggregation)."""
        result: list[dict[str, object]] = []
        for record in self._bridges.values():
            resources_dict: dict[str, float] | None = None
            if record.resources is not None:
                resources_dict = {
                    "cpu_usage_percent": record.resources.cpu_usage_percent,
                    "memory_usage_percent": record.resources.memory_usage_percent,
                    "disk_usage_percent": record.resources.disk_usage_percent,
                    "disk_free_gb": record.resources.disk_free_gb,
                }
            result.append(
                {
                    "host_id": record.host_id,
                    "status": record.status,
                    "resources": resources_dict,
                    "active_tasks": record.active_tasks or 0,
                    "uptime_seconds": record.uptime_seconds or 0,
                }
            )
        return result

    def get_claude_processes(self, host_id: str) -> list[ClaudeProcessInfo]:
        """Return claude process list for a given bridge."""
        record = self._bridges.get(host_id)
        if record is None:
            return []
        return list(record.claude_processes)

    @staticmethod
    def _to_detail(record: _BridgeRecord) -> AgentDetailResponse:
        return AgentDetailResponse(
            host_id=record.host_id,
            status=record.status,
            capabilities=list(record.capabilities),
            last_heartbeat_at=(
                record.last_heartbeat_at.isoformat() if record.last_heartbeat_at else None
            ),
            registered_at=record.registered_at.isoformat(),
            os_info=record.os_info,
            metadata=dict(record.metadata),
            uptime_seconds=record.uptime_seconds,
            active_tasks=record.active_tasks,
            resources=record.resources,
            claude_processes=list(record.claude_processes),
        )


# Module-level singleton so that both the WS endpoint and REST endpoint share state.
# ios_manager is injected lazily after the WebSocket module initializes.
def _make_registry() -> BridgeRegistryService:
    try:
        from app.api.routes.websocket import manager as _ios_manager  # noqa: PLC0415

        return BridgeRegistryService(ios_manager=_ios_manager)
    except Exception:
        return BridgeRegistryService()


bridge_registry = _make_registry()
