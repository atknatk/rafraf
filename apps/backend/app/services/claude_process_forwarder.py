"""Claude subprocess supervisor event forwarder (V1.x — Item 11).

Layer B (backend) of the supervisor pipeline. The Mac Go bridge emits 6
`event.claude.process.*` envelopes whenever a supervised claude subprocess
changes state (see `shared/feature-specs/V1x-claude-supervisor.md` §4); this
service:

1. Resolves `session_id → user_id` via :class:`SessionRepository` so we never
   broadcast a process event to the wrong tenant.
2. Wraps each typed payload in the standard server-to-client envelope dict
   (mirrors :class:`ClaudeStreamManager`) and pushes it to every iOS
   connection of that user via :meth:`ConnectionManager.send_to_user`.
3. Dedups ``healthcheck`` events per ``(user_id, session_id, status)`` over a
   short in-memory window so a noisy 1-second probe loop can't flood the
   client (Q6 user decision: state-transitions + 30s coalesce — the bridge
   already coalesces upstream; this layer is a defence-in-depth dedup with a
   shorter 5s window so the backend never re-sends an identical status to the
   same user faster than that).
4. For terminal-bad states (``stalled`` / ``crashed``) persists a
   :class:`ProactiveNotificationModel` row via
   :class:`ProactiveNotificationService` so push delivery is durable even
   when the iOS app is backgrounded.

Lazy singleton via :func:`get_claude_process_forwarder` mirrors
:func:`app.api.routes.agent_ws.get_claude_stream_manager`. The iOS-side
``ConnectionManager`` is injected at construction time (and the call site in
``agent_ws`` passes the actual singleton).

Auth posture: this forwarder only handles ALREADY-authenticated bridge
envelopes (gated by the API-key flow on the bridge WebSocket endpoint). The
opposite-direction ``command.claude.process.retry`` (iOS → backend → bridge)
lives in ``websocket.py`` and re-checks the JWT user_id against the resolved
session owner before dispatching.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import structlog

from app.core.database import async_session_factory
from app.schemas.messages import (
    ClaudeProcessCrashedPayload,
    ClaudeProcessDiagnosedPayload,
    ClaudeProcessHealthcheckPayload,
    ClaudeProcessRecoveredPayload,
    ClaudeProcessSpawnedPayload,
    ClaudeProcessStalledPayload,
    MessageDirection,
    MessageType,
)
from app.schemas.proactive_notification import (
    CreateProactiveNotification,
    NotificationPriority,
    ProactiveNotificationType,
)

if TYPE_CHECKING:
    from app.core.websocket import ConnectionManager

logger: structlog.stdlib.BoundLogger = structlog.get_logger()


# Healthcheck dedup window in seconds. The user-decision (Q6) is "state
# transitions + 30s coalesce", which the bridge enforces upstream; this is a
# tighter defence-in-depth window so the backend never re-emits an identical
# (user, session, status) row faster than every 5 seconds even if a misbehaving
# bridge floods us. Tuned short so legitimate state transitions still get
# through promptly.
_HEALTHCHECK_DEDUP_WINDOW_SECONDS = 5.0


class ClaudeProcessForwarder:
    """Fan out supervisor envelopes to iOS + persist proactive notifications."""

    def __init__(self, ios_manager: ConnectionManager | None) -> None:
        self._ios_manager: ConnectionManager | None = ios_manager
        # Per-(user_id, session_id, status) → monotonic timestamp of last send.
        # Bounded growth: new entries are added on every healthcheck, but a
        # supervisor instance lives for the duration of a single claude run
        # (minutes, not days) and on `crashed` / `completed` we drop the
        # session_id key. Worst-case memory is O(active_supervised_sessions ×
        # status_count) which is ≤ 3 × 6 = 18 entries on a fully saturated
        # bridge — trivially small.
        self._healthcheck_seen: dict[tuple[str, str, str], float] = {}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _resolve_session_owner(self, session_id: str) -> str | None:
        """Look up the ``user_id`` that owns ``session_id``.

        Returns ``None`` when the row is missing — caller logs + drops so an
        orphan envelope never leaks across tenants. Returns the stringified
        UUID (matches the keying ConnectionManager.send_to_user expects).
        """
        try:
            session_uuid = UUID(session_id)
        except ValueError:
            await logger.awarning(
                "claude_process_invalid_session_id",
                session_id=session_id,
            )
            return None

        # Local import keeps the module import graph thin and avoids the
        # circular dep through ``websocket.py`` that bites
        # :func:`agent_ws.get_claude_stream_manager`.
        from app.repositories.session_repo import SessionRepository  # noqa: PLC0415

        async with async_session_factory() as session:
            repo = SessionRepository(session)
            record = await repo.get_by_id(session_uuid)
            if record is None:
                return None
            return str(record.user_id)

    async def _push_to_user(
        self,
        *,
        user_id: str,
        msg_type: MessageType,
        payload: dict[str, object],
        session_id: str,
    ) -> int:
        """Build a server-to-client envelope dict and broadcast to a user."""
        if self._ios_manager is None:
            await logger.adebug(
                "claude_process_forwarder_no_ios_manager",
                msg_type=msg_type.value,
                user_id=user_id,
            )
            return 0
        envelope: dict[str, object] = {
            "id": str(uuid4()),
            "type": msg_type.value,
            "content": payload,
            "metadata": {
                "timestamp": datetime.now(tz=UTC).isoformat(),
                "session_id": session_id,
                "direction": MessageDirection.SERVER_TO_CLIENT.value,
            },
        }
        sent: int = await self._ios_manager.send_to_user(user_id, envelope)
        await logger.adebug(
            "claude_process_forwarded",
            msg_type=msg_type.value,
            user_id=user_id,
            session_id=session_id,
            sessions_reached=sent,
        )
        return sent

    async def _persist_proactive_notification(
        self,
        *,
        user_id: str,
        session_id: str,
        notification_type: ProactiveNotificationType,
        priority: NotificationPriority,
        title: str,
        body: str,
        source_event_suffix: str,
        deep_link: str | None = None,
    ) -> None:
        """Persist a :class:`ProactiveNotificationModel` row (best-effort).

        Failures here MUST NOT break the WS forward path — the iOS user has
        already received the live envelope; the proactive row is purely for
        durable push when the app is backgrounded.

        ``source_event`` is namespaced
        (``claude.process.<suffix>:<session_id>``) so the dedup branch in
        :meth:`ProactiveNotificationService.create_notification` doesn't double
        up when a flapping process re-stalls within the same session.
        """
        try:
            user_uuid = UUID(user_id)
        except ValueError:
            await logger.awarning(
                "claude_process_proactive_invalid_user_id",
                user_id=user_id,
            )
            return

        # Lazy import to keep module import time low and avoid pulling the
        # full notification stack into hot paths that never hit a stalled or
        # crashed event.
        from app.services.proactive_notification_service import (  # noqa: PLC0415
            ProactiveNotificationService,
        )

        try:
            async with async_session_factory() as db:
                service = ProactiveNotificationService(db)
                await service.create_notification(
                    CreateProactiveNotification(
                        user_id=user_uuid,
                        type=notification_type,
                        priority=priority,
                        title=title,
                        body=body,
                        source="claude_supervisor",
                        source_event=f"claude.process.{source_event_suffix}:{session_id}",
                        deep_link=deep_link,
                        metadata={"session_id": session_id},
                    ),
                )
                await db.commit()
        except Exception:
            # Audit/notification persistence failures must never break the
            # WebSocket forward path — log and continue.
            await logger.aexception(
                "claude_process_proactive_persist_failed",
                user_id=user_id,
                session_id=session_id,
                source_event_suffix=source_event_suffix,
            )

    def _healthcheck_should_forward(
        self,
        *,
        user_id: str,
        session_id: str,
        status: str,
    ) -> bool:
        """Return ``True`` if this `(user, session, status)` is outside the dedup window.

        Side-effects: updates the `_healthcheck_seen` map on the True branch
        so the next call within the window short-circuits. Uses
        :func:`time.monotonic` so wall-clock jumps don't accidentally re-open
        the dedup window.
        """
        key = (user_id, session_id, status)
        now = time.monotonic()
        last = self._healthcheck_seen.get(key)
        if last is not None and (now - last) < _HEALTHCHECK_DEDUP_WINDOW_SECONDS:
            return False
        self._healthcheck_seen[key] = now
        return True

    def _drop_healthcheck_dedup(self, session_id: str) -> None:
        """Drop all dedup state for ``session_id`` (called on terminal events)."""
        # Iterate over a snapshot so we can mutate the dict.
        for key in [k for k in self._healthcheck_seen if k[1] == session_id]:
            self._healthcheck_seen.pop(key, None)

    # ------------------------------------------------------------------
    # 6 forward_<type> methods (one per outbound bridge → backend event).
    # ------------------------------------------------------------------

    async def forward_spawned(self, raw_payload: dict[str, object]) -> int:
        """Forward `event.claude.process.spawned` to the owning user."""
        try:
            payload = ClaudeProcessSpawnedPayload.model_validate(raw_payload)
        except Exception:
            await logger.awarning(
                "claude_process_spawned_invalid_payload",
                payload_keys=list(raw_payload.keys()),
            )
            return 0

        user_id = await self._resolve_session_owner(payload.session_id)
        if user_id is None:
            await logger.awarning(
                "claude_process_spawned_orphan_session",
                session_id=payload.session_id,
            )
            return 0

        sent = await self._push_to_user(
            user_id=user_id,
            msg_type=MessageType.CLAUDE_PROCESS_SPAWNED,
            payload=payload.model_dump(mode="json"),
            session_id=payload.session_id,
        )
        await logger.ainfo(
            "claude_process_spawned_forwarded",
            session_id=payload.session_id,
            user_id=user_id,
            pid=payload.pid,
            sessions_reached=sent,
        )
        return sent

    async def forward_healthcheck(self, raw_payload: dict[str, object]) -> int:
        """Forward `event.claude.process.healthcheck` (with 5s per-(user,session,status) dedup)."""
        try:
            payload = ClaudeProcessHealthcheckPayload.model_validate(raw_payload)
        except Exception:
            await logger.awarning(
                "claude_process_healthcheck_invalid_payload",
                payload_keys=list(raw_payload.keys()),
            )
            return 0

        user_id = await self._resolve_session_owner(payload.session_id)
        if user_id is None:
            await logger.awarning(
                "claude_process_healthcheck_orphan_session",
                session_id=payload.session_id,
            )
            return 0

        if not self._healthcheck_should_forward(
            user_id=user_id,
            session_id=payload.session_id,
            status=payload.status,
        ):
            await logger.adebug(
                "claude_process_healthcheck_deduped",
                session_id=payload.session_id,
                user_id=user_id,
                status=payload.status,
            )
            return 0

        return await self._push_to_user(
            user_id=user_id,
            msg_type=MessageType.CLAUDE_PROCESS_HEALTHCHECK,
            payload=payload.model_dump(mode="json"),
            session_id=payload.session_id,
        )

    async def forward_stalled(self, raw_payload: dict[str, object]) -> int:
        """Forward `event.claude.process.stalled` + persist a proactive notification."""
        try:
            payload = ClaudeProcessStalledPayload.model_validate(raw_payload)
        except Exception:
            await logger.awarning(
                "claude_process_stalled_invalid_payload",
                payload_keys=list(raw_payload.keys()),
            )
            return 0

        user_id = await self._resolve_session_owner(payload.session_id)
        if user_id is None:
            await logger.awarning(
                "claude_process_stalled_orphan_session",
                session_id=payload.session_id,
            )
            return 0

        sent = await self._push_to_user(
            user_id=user_id,
            msg_type=MessageType.CLAUDE_PROCESS_STALLED,
            payload=payload.model_dump(mode="json"),
            session_id=payload.session_id,
        )
        await self._persist_proactive_notification(
            user_id=user_id,
            session_id=payload.session_id,
            notification_type=ProactiveNotificationType.issue_detected,
            priority=NotificationPriority.normal,
            title="Claude takıldı",
            body=(
                f"Süreç {payload.stale_for_ms // 1000} saniyedir yanıt vermiyor. "
                "Otomatik teşhis çalışıyor."
            ),
            source_event_suffix="stalled",
        )
        await logger.ainfo(
            "claude_process_stalled_forwarded",
            session_id=payload.session_id,
            user_id=user_id,
            pid=payload.pid,
            stale_for_ms=payload.stale_for_ms,
            sessions_reached=sent,
        )
        return sent

    async def forward_crashed(self, raw_payload: dict[str, object]) -> int:
        """Forward `event.claude.process.crashed` + persist an urgent proactive notification."""
        try:
            payload = ClaudeProcessCrashedPayload.model_validate(raw_payload)
        except Exception:
            await logger.awarning(
                "claude_process_crashed_invalid_payload",
                payload_keys=list(raw_payload.keys()),
            )
            return 0

        user_id = await self._resolve_session_owner(payload.session_id)
        if user_id is None:
            await logger.awarning(
                "claude_process_crashed_orphan_session",
                session_id=payload.session_id,
            )
            return 0

        sent = await self._push_to_user(
            user_id=user_id,
            msg_type=MessageType.CLAUDE_PROCESS_CRASHED,
            payload=payload.model_dump(mode="json"),
            session_id=payload.session_id,
        )
        # Crash is terminal — drop dedup state so a fresh session reusing the
        # same UUID (post-retry) starts with a clean slate.
        self._drop_healthcheck_dedup(payload.session_id)
        await self._persist_proactive_notification(
            user_id=user_id,
            session_id=payload.session_id,
            notification_type=ProactiveNotificationType.ci_failure,
            priority=NotificationPriority.urgent,
            title="Claude çöktü",
            body=(
                f"Süreç {payload.exit_code} koduyla sonlandı"
                f"{f' ({payload.signal})' if payload.signal else ''}. "
                "Yeniden denemek için sohbete dönün."
            ),
            source_event_suffix="crashed",
        )
        await logger.ainfo(
            "claude_process_crashed_forwarded",
            session_id=payload.session_id,
            user_id=user_id,
            pid=payload.pid,
            exit_code=payload.exit_code,
            sessions_reached=sent,
        )
        return sent

    async def forward_recovered(self, raw_payload: dict[str, object]) -> int:
        """Forward `event.claude.process.recovered` to the owning user."""
        try:
            payload = ClaudeProcessRecoveredPayload.model_validate(raw_payload)
        except Exception:
            await logger.awarning(
                "claude_process_recovered_invalid_payload",
                payload_keys=list(raw_payload.keys()),
            )
            return 0

        # Owner lookup uses the OLD session_id (the one the user has been
        # tracking on iOS). For self-recovery old==new, so this is the same as
        # using new_session_id; for manual_retry the new session is a fresh
        # UUID owned by the same user — using old keeps the lookup stable.
        user_id = await self._resolve_session_owner(payload.old_session_id)
        if user_id is None:
            await logger.awarning(
                "claude_process_recovered_orphan_session",
                old_session_id=payload.old_session_id,
                new_session_id=payload.new_session_id,
            )
            return 0

        # Recovery is also a terminal-ish transition for the OLD session id;
        # clear dedup so the fresh session reusing the slot gets fresh state.
        self._drop_healthcheck_dedup(payload.old_session_id)
        return await self._push_to_user(
            user_id=user_id,
            msg_type=MessageType.CLAUDE_PROCESS_RECOVERED,
            payload=payload.model_dump(mode="json"),
            session_id=payload.new_session_id,
        )

    async def forward_diagnosed(self, raw_payload: dict[str, object]) -> int:
        """Forward `event.claude.process.diagnosed` to the owning user."""
        try:
            payload = ClaudeProcessDiagnosedPayload.model_validate(raw_payload)
        except Exception:
            await logger.awarning(
                "claude_process_diagnosed_invalid_payload",
                payload_keys=list(raw_payload.keys()),
            )
            return 0

        user_id = await self._resolve_session_owner(payload.session_id)
        if user_id is None:
            await logger.awarning(
                "claude_process_diagnosed_orphan_session",
                session_id=payload.session_id,
            )
            return 0

        return await self._push_to_user(
            user_id=user_id,
            msg_type=MessageType.CLAUDE_PROCESS_DIAGNOSED,
            payload=payload.model_dump(mode="json"),
            session_id=payload.session_id,
        )


# ---------------------------------------------------------------------------
# Lazy singleton wiring (mirror of get_claude_stream_manager).
# ---------------------------------------------------------------------------

_claude_process_forwarder: ClaudeProcessForwarder | None = None


def get_claude_process_forwarder() -> ClaudeProcessForwarder:
    """Get or create the global supervisor forwarder.

    The iOS-side ``ConnectionManager`` is imported lazily to avoid the import
    cycle through :mod:`app.api.routes.websocket` (which itself imports a
    handful of services). Mirrors the wiring of
    :func:`app.api.routes.agent_ws.get_claude_stream_manager`.
    """
    global _claude_process_forwarder  # noqa: PLW0603
    if _claude_process_forwarder is None:
        from app.api.routes.websocket import manager as ios_manager  # noqa: PLC0415

        _claude_process_forwarder = ClaudeProcessForwarder(ios_manager=ios_manager)
    return _claude_process_forwarder


def reset_claude_process_forwarder_for_tests() -> None:
    """Reset the lazy singleton so unit tests can inject fresh state.

    Test-only helper — production code never calls this. Kept module-private-
    ish (single-leading-underscore prefix removed only because pytest fixtures
    sometimes forbid private imports across packages).
    """
    global _claude_process_forwarder  # noqa: PLW0603
    _claude_process_forwarder = None
