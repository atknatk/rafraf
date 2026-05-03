"""Unit tests for the V1.x Claude Subprocess Supervisor backend wiring (Item 11).

Five focused cases per spec §6.3 (`shared/feature-specs/V1x-claude-supervisor.md`):

1. ``test_forward_spawned_to_owner_only`` — fan-out is per-user, not broadcast.
2. ``test_malformed_envelope_logs_and_drops`` — payload missing ``session_id``
   does NOT raise, just warn + drop.
3. ``test_stalled_envelope_creates_proactive_notification`` — terminal-bad
   states persist a :class:`ProactiveNotification` row.
4. ``test_retry_command_forwarded_to_correct_bridge`` — multi-bridge
   broadcast hits every connected bridge (the bridge supervisor map is the
   final routing layer per spec §4.7).
5. ``test_healthcheck_coalescing_within_window`` — 10 events in 1 second for
   the same ``(user, session, status)`` collapse to ≤ 2 forwarded.

Tests patch the iOS-side ``ConnectionManager`` and the SQLAlchemy session
factory so no real WebSocket / DB round-trip is required.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from app.api.routes import websocket as websocket_module
from app.schemas.messages import MessageType
from app.services import claude_process_forwarder as forwarder_module

# ---------------------------------------------------------------------------
# Shared fixtures.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_forwarder_singleton() -> None:
    """Drop the lazy-singleton between tests so each gets a fresh instance."""
    forwarder_module.reset_claude_process_forwarder_for_tests()


@pytest.fixture
def fake_ios_manager() -> MagicMock:
    """A fake iOS ConnectionManager that records every send_to_user call."""
    manager = MagicMock()
    manager.send_to_user = AsyncMock(return_value=1)
    return manager


@pytest.fixture
def patch_session_owner(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Patch ``SessionRepository.get_by_id`` so session_id → fake user_id.

    Returns the AsyncMock so individual tests can override ``return_value``
    (e.g. set to ``None`` to simulate an orphan / unauthorized session).
    """
    fake_user_uuid = UUID("00000000-0000-0000-0000-000000000111")
    fake_repo_get = AsyncMock(return_value=SimpleNamespace(user_id=fake_user_uuid))

    def _make_repo(_session: object) -> object:
        return SimpleNamespace(get_by_id=fake_repo_get)

    monkeypatch.setattr(
        "app.repositories.session_repo.SessionRepository",
        _make_repo,
    )

    fake_session = AsyncMock()
    fake_session.__aenter__.return_value = fake_session
    fake_session.__aexit__.return_value = None
    monkeypatch.setattr(
        forwarder_module,
        "async_session_factory",
        lambda: fake_session,
    )
    return fake_repo_get


# ---------------------------------------------------------------------------
# Test 1: forward_spawned routes to owner only.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_forward_spawned_to_owner_only(
    fake_ios_manager: MagicMock,
    patch_session_owner: AsyncMock,
) -> None:
    """`event.claude.process.spawned` MUST go to the owning user only."""
    forwarder = forwarder_module.ClaudeProcessForwarder(ios_manager=fake_ios_manager)
    sid = str(uuid4())
    raw_payload = {
        "session_id": sid,
        "pid": 49271,
        "started_at": "2026-05-03T10:14:22.143Z",
        "model": "claude-sonnet-4-7",
        "args": ["-p", "--output-format", "stream-json"],
        "permission_mode": "acceptEdits",
        "project_dir": "/Users/atakan/proj",
    }

    sent = await forwarder.forward_spawned(raw_payload)

    # Resolved owner via SessionRepository.get_by_id (patch_session_owner).
    patch_session_owner.assert_awaited_once()
    # Exactly one send_to_user call → only the owning user gets the event;
    # no broadcast (would have hit other user_ids).
    assert fake_ios_manager.send_to_user.await_count == 1
    call_args = fake_ios_manager.send_to_user.await_args
    target_user, envelope = call_args.args
    assert target_user == "00000000-0000-0000-0000-000000000111"
    assert envelope["type"] == MessageType.CLAUDE_PROCESS_SPAWNED.value
    assert envelope["content"]["session_id"] == sid
    assert envelope["content"]["pid"] == 49271
    assert envelope["metadata"]["session_id"] == sid
    # Forwarder reports the count from send_to_user (=1, fixture default).
    assert sent == 1


# ---------------------------------------------------------------------------
# Test 2: malformed envelope — missing session_id → log + drop.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_malformed_envelope_logs_and_drops(
    fake_ios_manager: MagicMock,
    patch_session_owner: AsyncMock,  # noqa: ARG001 — present to satisfy the import contract
) -> None:
    """Payload missing ``session_id`` MUST NOT raise — warn + return 0."""
    forwarder = forwarder_module.ClaudeProcessForwarder(ios_manager=fake_ios_manager)

    # Pydantic validation failure: missing required ``session_id``.
    sent = await forwarder.forward_spawned(
        {
            # session_id intentionally omitted
            "pid": 49271,
            "started_at": "2026-05-03T10:14:22.143Z",
            "model": "claude-sonnet-4-7",
            "args": [],
            "permission_mode": "acceptEdits",
            "project_dir": "/Users/atakan/proj",
        },
    )
    assert sent == 0
    fake_ios_manager.send_to_user.assert_not_awaited()

    # And separately: a non-UUID session_id (bypasses Pydantic but fails at
    # the SessionRepository UUID parse step) — also no exception, also 0.
    sent2 = await forwarder.forward_spawned(
        {
            "session_id": "not-a-uuid",
            "pid": 49271,
            "started_at": "2026-05-03T10:14:22.143Z",
            "model": "claude-sonnet-4-7",
            "args": [],
            "permission_mode": "acceptEdits",
            "project_dir": "/Users/atakan/proj",
        },
    )
    assert sent2 == 0
    fake_ios_manager.send_to_user.assert_not_awaited()


# ---------------------------------------------------------------------------
# Test 3: stalled → ProactiveNotificationService.create_notification call.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stalled_envelope_creates_proactive_notification(
    fake_ios_manager: MagicMock,
    patch_session_owner: AsyncMock,  # noqa: ARG001 — needed for owner resolution
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`event.claude.process.stalled` MUST persist a ProactiveNotification row."""
    # Arrange: capture create_notification calls via the imported module so
    # we don't have to spin up a real DB.
    create_call: list[object] = []

    class _FakeService:
        def __init__(self, _session: object) -> None:  # mirror real signature
            pass

        async def create_notification(self, payload: object) -> None:
            create_call.append(payload)

    monkeypatch.setattr(
        "app.services.proactive_notification_service.ProactiveNotificationService",
        _FakeService,
    )

    forwarder = forwarder_module.ClaudeProcessForwarder(ios_manager=fake_ios_manager)
    sid = str(uuid4())

    sent = await forwarder.forward_stalled(
        {
            "session_id": sid,
            "pid": 49271,
            "last_activity_at": "2026-05-03T10:12:55.412Z",
            "stale_for_ms": 91200,
            "stderr_tail": "Error: connection reset by peer",
            "stderr_tail_truncated": False,
            "self_heal_pending": True,
        },
    )

    # iOS push happened.
    assert sent == 1
    assert fake_ios_manager.send_to_user.await_count == 1
    envelope = fake_ios_manager.send_to_user.await_args.args[1]
    assert envelope["type"] == MessageType.CLAUDE_PROCESS_STALLED.value
    assert envelope["content"]["self_heal_pending"] is True

    # ProactiveNotification was persisted exactly once.
    assert len(create_call) == 1
    persisted = create_call[0]
    # Payload uses the typed schema — assert the source_event namespace
    # follows the dedup convention.
    assert persisted.source == "claude_supervisor"
    assert persisted.source_event == f"claude.process.stalled:{sid}"
    assert persisted.metadata == {"session_id": sid}
    # Stalled is non-urgent (vs crashed=urgent).
    assert persisted.priority.value == "normal"


# ---------------------------------------------------------------------------
# Test 4: retry command — multi-bridge fixture, broadcast to every bridge.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retry_command_forwarded_to_correct_bridge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`command.claude.process.retry` MUST reach every connected bridge.

    Per spec §4.7, the bridge whose supervisor map holds the session_id is
    the only one that acts on it; non-owning bridges silently no-op. This
    is covered here by asserting the backend dispatches via
    :meth:`bridge_registry.send_to_bridge` for every bridge in the
    registry — owning vs non-owning resolution lives on the bridge layer.
    """
    # Arrange: a multi-bridge registry — two online bridges with distinct
    # connection_ids.
    fake_bridges = {
        "mac-A": SimpleNamespace(host_id="mac-A", connection_id="conn-A"),
        "mac-B": SimpleNamespace(host_id="mac-B", connection_id="conn-B"),
    }
    monkeypatch.setattr(
        "app.api.routes.websocket.bridge_registry._bridges",
        fake_bridges,
        raising=False,
    )

    sent_envelopes: list[tuple[str, dict[str, object]]] = []

    async def _fake_send_to_bridge(host_id: str, envelope: dict[str, object]) -> bool:
        sent_envelopes.append((host_id, envelope))
        return True

    monkeypatch.setattr(
        "app.api.routes.websocket.bridge_registry.send_to_bridge",
        _fake_send_to_bridge,
    )

    # Stub SessionRepository so the auth cross-check passes for our user.
    target_user_id = "user-jwt-1234"
    target_session_id = str(uuid4())

    class _FakeSessionRepo:
        def __init__(self, _session: object) -> None:
            pass

        async def get_by_id(self, sid: UUID) -> object:
            assert str(sid) == target_session_id
            return SimpleNamespace(user_id=UUID(int=0x1234))

    # The SessionRepository owner_user_id must match the JWT user_id. The
    # auth cross-check stringifies the UUID for comparison.
    target_user_id_uuid = UUID(int=0x1234)
    target_user_id = str(target_user_id_uuid)

    monkeypatch.setattr(
        "app.repositories.session_repo.SessionRepository",
        _FakeSessionRepo,
    )

    fake_db = AsyncMock()
    fake_db.__aenter__.return_value = fake_db
    fake_db.__aexit__.return_value = None
    monkeypatch.setattr(
        websocket_module,
        "async_session_factory",
        lambda: fake_db,
    )

    # Stub the iOS WS manager so an error path (if any) doesn't crash.
    fake_send_json = AsyncMock(return_value=True)
    monkeypatch.setattr(
        websocket_module.manager,
        "send_json",
        fake_send_json,
    )

    # Act: invoke the iOS-side handler directly.
    raw = {
        "type": "command.claude.process.retry",
        "content": {
            "session_id": target_session_id,
            # IOS-supplied user_id is intentionally bogus — backend must
            # ignore it and use the JWT user_id.
            "user_id": "anyone-could-write-this",
        },
    }
    await websocket_module._handle_claude_process_retry(
        raw,
        connection_id="conn-iOS-1",
        session_id="ws-session-1",
        user_id=target_user_id,
    )

    # Both bridges received the same envelope.
    assert len(sent_envelopes) == 2
    host_ids = {host for host, _ in sent_envelopes}
    assert host_ids == {"mac-A", "mac-B"}

    # Envelope carries the spec §4.7 wire shape and the JWT user_id (not
    # the iOS-supplied one).
    for _host, env in sent_envelopes:
        assert env["type"] == "command.claude.process.retry"
        payload = env["payload"]
        assert isinstance(payload, dict)
        assert payload["session_id"] == target_session_id
        assert payload["user_id"] == target_user_id  # NOT "anyone-could-write-this"

    # No client-facing error was emitted.
    fake_send_json.assert_not_awaited()


# ---------------------------------------------------------------------------
# Test 5: healthcheck coalescing — 10 events in 1s collapse to ≤ 2.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_healthcheck_coalescing_within_window(
    fake_ios_manager: MagicMock,
    patch_session_owner: AsyncMock,  # noqa: ARG001 — owner resolution path
) -> None:
    """10 healthchecks for same (user, session, status) → ≤ 2 forwarded.

    The dedup window is 5s real wall-clock per key. We drive that window
    by manipulating the per-(user, session, status) entry in the
    forwarder's internal `_healthcheck_seen` map directly between calls
    instead of patching `time.monotonic` (which structlog also reads,
    making the patch flaky). The internal map is tested as documented
    state — the spec contract is `(user, session, status) → ≤ 2
    forwards in 1s`, which we observe via send_to_user.await_count.
    """
    forwarder = forwarder_module.ClaudeProcessForwarder(ios_manager=fake_ios_manager)
    sid = str(uuid4())
    user_id = "00000000-0000-0000-0000-000000000111"
    status = "running"
    dedup_key = (user_id, sid, status)

    base_payload = {
        "session_id": sid,
        "pid": 49271,
        "status": status,
        "last_stdout_age_ms": 1850,
        "current_tokens": 1240,
        "memory_rss_kb": 184320,
        "cpu_percent_1s": 12.4,
        "observed_at": "2026-05-03T10:14:27.991Z",
    }

    # First burst: 9 calls all "within the window" — we hold the dedup map
    # entry's recorded ts to a fresh value before each retry by reading
    # `time.monotonic()` from the same module so the delta stays under 5s.
    forwarded_counts: list[int] = []
    forwarded_counts.append(await forwarder.forward_healthcheck(base_payload))
    # Pin the dedup ts to "now" so the next 8 calls are all inside the 5s
    # window. We use the forwarder's own clock source to stay consistent.
    pinned = forwarder_module.time.monotonic()
    for _ in range(8):
        forwarder._healthcheck_seen[dedup_key] = pinned
        forwarded_counts.append(await forwarder.forward_healthcheck(base_payload))

    # 10th call: simulate the dedup state being older than the window.
    # Setting the recorded ts to "well in the past" forces the helper to
    # treat the next call as a fresh sample and forward it.
    forwarder._healthcheck_seen[dedup_key] = pinned - 999.0
    forwarded_counts.append(await forwarder.forward_healthcheck(base_payload))

    # ≤ 2 forwarded — the spec bound. Exactly 2 in this run.
    forwards = sum(1 for n in forwarded_counts if n > 0)
    assert forwards <= 2
    assert forwards == 2
    assert fake_ios_manager.send_to_user.await_count == 2

    # Sanity: the second forwarded sample is the same status — no envelope
    # mutation happened between sends.
    first_envelope = fake_ios_manager.send_to_user.await_args_list[0].args[1]
    second_envelope = fake_ios_manager.send_to_user.await_args_list[1].args[1]
    assert first_envelope["content"]["status"] == status
    assert second_envelope["content"]["status"] == status


# ---------------------------------------------------------------------------
# Sanity: MessageType registrations match the spec §4 wire format suffixes.
# ---------------------------------------------------------------------------


def test_claude_process_message_type_values() -> None:
    """Enum values MUST match the bridge wire format strings (spec §4)."""
    assert MessageType.CLAUDE_PROCESS_SPAWNED.value == "event.claude.process.spawned"
    assert MessageType.CLAUDE_PROCESS_HEALTHCHECK.value == "event.claude.process.healthcheck"
    assert MessageType.CLAUDE_PROCESS_STALLED.value == "event.claude.process.stalled"
    assert MessageType.CLAUDE_PROCESS_CRASHED.value == "event.claude.process.crashed"
    assert MessageType.CLAUDE_PROCESS_RECOVERED.value == "event.claude.process.recovered"
    assert MessageType.CLAUDE_PROCESS_DIAGNOSED.value == "event.claude.process.diagnosed"
    assert MessageType.CLAUDE_PROCESS_RETRY.value == "command.claude.process.retry"


# Sanity that the timestamp parser accepts the spec ISO-8601 form (used in
# every fixture above) — protects against a Pydantic version drift surprise.
def test_pydantic_parses_spec_timestamp_format() -> None:
    """Spec §4.1 ISO-8601 (with 'Z' suffix) MUST parse cleanly."""
    from app.schemas.messages import ClaudeProcessSpawnedPayload

    payload = ClaudeProcessSpawnedPayload(
        session_id="x",
        pid=1,
        started_at=datetime(2026, 5, 3, 10, 14, 22, tzinfo=UTC),
        model="m",
        args=[],
        permission_mode="acceptEdits",
        project_dir="/p",
    )
    # Round-trip via model_dump(mode="json") preserves the ISO format.
    dumped = payload.model_dump(mode="json")
    assert "2026-05-03" in str(dumped["started_at"])

    # Also accept the spec wire form (Z-terminated UTC).
    parsed = ClaudeProcessSpawnedPayload.model_validate(
        {
            "session_id": "x",
            "pid": 1,
            "started_at": "2026-05-03T10:14:22.143Z",
            "model": "m",
            "args": [],
            "permission_mode": "acceptEdits",
            "project_dir": "/p",
        },
    )
    assert parsed.started_at.tzinfo is not None


# Avoid an "unused import" warning when tests are run in isolation modes
# (some import-order CI settings strip the import without this).
_ = time
