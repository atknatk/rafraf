"""Host Agent registry and health monitoring service.

Manages agent registration, heartbeat tracking, and stale-agent detection.
Uses an in-memory store for fast access (no DB dependency in F1).
"""

import asyncio
import contextlib
from datetime import UTC, datetime

import structlog

from app.schemas.agent import (
    AgentCapability,
    AgentDetailResponse,
    AgentHeartbeatPayload,
    AgentListResponse,
    AgentRegisterPayload,
    AgentStatus,
    AgentSummary,
    ResourceInfo,
)

logger: structlog.stdlib.BoundLogger = structlog.get_logger()


class _AgentRecord:
    """Internal mutable record for a registered agent."""

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


class AgentRegistryService:
    """Singleton-style service that manages the in-memory agent registry.

    Thread-safety is ensured by asyncio's single-threaded event loop.
    """

    def __init__(
        self,
        heartbeat_timeout_seconds: int = 90,
        stale_check_interval_seconds: int = 30,
    ) -> None:
        self._agents: dict[str, _AgentRecord] = {}
        self._heartbeat_timeout = heartbeat_timeout_seconds
        self._stale_check_interval = stale_check_interval_seconds
        self._stale_task: asyncio.Task[None] | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start_stale_checker(self) -> None:
        """Start the background task that marks stale agents as offline."""
        if self._stale_task is None or self._stale_task.done():
            self._stale_task = asyncio.create_task(self._stale_check_loop())
            await logger.ainfo("agent_stale_checker_started")

    async def stop_stale_checker(self) -> None:
        """Cancel the background stale-check task."""
        if self._stale_task is not None and not self._stale_task.done():
            self._stale_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._stale_task
            await logger.ainfo("agent_stale_checker_stopped")

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    async def register_agent(
        self,
        payload: AgentRegisterPayload,
        connection_id: str,
    ) -> bool:
        """Register or re-register an agent.

        Returns True if newly registered, False if updated.
        """
        existing = self._agents.get(payload.host_id)
        is_new = existing is None

        record = _AgentRecord(
            host_id=payload.host_id,
            capabilities=list(payload.capabilities),
            os_info=payload.os_info,
            version=payload.version,
            connection_id=connection_id,
        )

        self._agents[payload.host_id] = record

        await logger.ainfo(
            "agent_registered",
            host_id=payload.host_id,
            is_new=is_new,
            capabilities=[c.value for c in payload.capabilities],
        )
        return is_new

    # ------------------------------------------------------------------
    # Heartbeat
    # ------------------------------------------------------------------

    async def process_heartbeat(self, payload: AgentHeartbeatPayload) -> bool:
        """Update agent state from a heartbeat message.

        Returns True if the agent was found, False otherwise.
        """
        record = self._agents.get(payload.host_id)
        if record is None:
            await logger.awarning(
                "heartbeat_unknown_agent",
                host_id=payload.host_id,
            )
            return False

        record.last_heartbeat_at = datetime.now(tz=UTC)
        record.status = payload.status
        record.uptime_seconds = payload.uptime_seconds
        record.active_tasks = payload.active_tasks
        record.resources = payload.resources

        await logger.adebug(
            "agent_heartbeat_processed",
            host_id=payload.host_id,
            status=payload.status.value,
        )
        return True

    # ------------------------------------------------------------------
    # Disconnection
    # ------------------------------------------------------------------

    async def mark_disconnected(self, host_id: str) -> None:
        """Mark an agent as offline upon WebSocket disconnect."""
        record = self._agents.get(host_id)
        if record is not None:
            record.status = AgentStatus.OFFLINE
            await logger.ainfo("agent_disconnected", host_id=host_id)

    async def unregister_by_connection(self, connection_id: str) -> str | None:
        """Find the agent associated with a connection and mark it offline.

        Returns the host_id if found, None otherwise.
        """
        for record in self._agents.values():
            if record.connection_id == connection_id:
                record.status = AgentStatus.OFFLINE
                await logger.ainfo(
                    "agent_disconnected_by_connection",
                    host_id=record.host_id,
                    connection_id=connection_id,
                )
                return record.host_id
        return None

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    async def list_agents(self, status_filter: AgentStatus | None = None) -> AgentListResponse:
        """Return a summary of all registered agents."""
        agents: list[AgentSummary] = []
        online_count = 0
        for record in self._agents.values():
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
        """Return detail for a single agent, or None if not found."""
        record = self._agents.get(host_id)
        if record is None:
            return None
        return self._to_detail(record)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _stale_check_loop(self) -> None:
        """Periodically mark agents that missed heartbeats as offline."""
        try:
            while True:
                await asyncio.sleep(self._stale_check_interval)
                now = datetime.now(tz=UTC)
                for record in self._agents.values():
                    if record.status == AgentStatus.OFFLINE:
                        continue
                    if record.last_heartbeat_at is None:
                        continue
                    elapsed = (now - record.last_heartbeat_at).total_seconds()
                    if elapsed > self._heartbeat_timeout:
                        await logger.awarning(
                            "agent_stale_detected",
                            host_id=record.host_id,
                            elapsed_seconds=elapsed,
                        )
                        record.status = AgentStatus.OFFLINE
        except asyncio.CancelledError:
            pass

    @staticmethod
    def _to_summary(record: _AgentRecord) -> AgentSummary:
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

    @staticmethod
    def _to_detail(record: _AgentRecord) -> AgentDetailResponse:
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
        )


# Module-level singleton so that both the WS endpoint and REST endpoint share state.
agent_registry = AgentRegistryService()
