"""Unit tests for agent_ws.py module-level handlers.

Focused on the T1.2 ``event.usage.report`` broadcast path and the
T1.2-fix ``event.session.title`` / ``event.session.pr_opened`` storage
paths — we exercise them in isolation by patching the ``ios_manager``,
``claude_stream_manager``, and ``SessionRepository`` so no real WebSocket
/ DB round-trip is required.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from prometheus_client.parser import text_string_to_metric_families

from app.api.routes import agent_ws as agent_ws_module
from app.core import metrics as _metrics
from app.schemas.messages import MessageType


@pytest.fixture
def fake_ios_manager(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Patch the iOS-side ConnectionManager singleton with a mock."""
    fake = MagicMock()
    fake.send_to_user = AsyncMock(return_value=2)
    fake.get_active_user_ids = MagicMock(return_value={"user-A", "user-B"})
    monkeypatch.setattr(
        "app.api.routes.websocket.manager",
        fake,
        raising=False,
    )
    return fake


@pytest.fixture
def fake_csm(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Replace get_claude_stream_manager() with a mock that records forwards."""
    fake = MagicMock()
    fake.forward_usage_report = AsyncMock(return_value=2)
    fake.forward_session_title = AsyncMock(return_value=1)
    fake.forward_session_pr_opened = AsyncMock(return_value=1)
    monkeypatch.setattr(
        agent_ws_module,
        "get_claude_stream_manager",
        lambda: fake,
    )
    return fake


@pytest.fixture
def fake_session_owner(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Patch _resolve_session_owner with an AsyncMock for direct control.

    Returns the AsyncMock so individual tests can override the resolved
    owner (or set it to ``None`` to simulate an orphan session row).
    """
    resolver = AsyncMock(return_value="owner-user-id")
    monkeypatch.setattr(
        agent_ws_module,
        "_resolve_session_owner",
        resolver,
    )
    return resolver


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_ios_manager")
async def test_handle_usage_report_broadcasts_to_every_active_user(
    fake_csm: MagicMock,
) -> None:
    """Each active iOS user MUST receive a forward_usage_report call."""
    raw = {
        "type": "event.usage.report",
        "payload": {
            "five_hour_pct": 73,
            "seven_day_pct": 41,
            "five_hour_resets_at": 1735689600,
            "seven_day_resets_at": 1736294400,
            "reported_at": 1735680000,
        },
    }
    await agent_ws_module._handle_usage_report(raw)

    # 2 active users → 2 forwarder invocations.
    assert fake_csm.forward_usage_report.await_count == 2
    forwarded_users = {
        call.kwargs["user_id"] for call in fake_csm.forward_usage_report.await_args_list
    }
    assert forwarded_users == {"user-A", "user-B"}

    # The payload fields propagate verbatim.
    sample = fake_csm.forward_usage_report.await_args_list[0]
    assert sample.kwargs["five_hour_pct"] == 73
    assert sample.kwargs["seven_day_pct"] == 41
    assert sample.kwargs["five_hour_resets_at"] == 1735689600
    assert sample.kwargs["seven_day_resets_at"] == 1736294400
    assert sample.kwargs["reported_at"] == 1735680000


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_ios_manager")
async def test_handle_usage_report_falls_back_to_content_key(
    fake_csm: MagicMock,
) -> None:
    """Legacy bridges that put fields under ``content`` must still work."""
    raw = {
        "type": "event.usage.report",
        "content": {
            "five_hour_pct": 5,
            "seven_day_pct": 2,
            "five_hour_resets_at": 1735689600,
            "seven_day_resets_at": 1736294400,
            "reported_at": 1735680000,
        },
    }
    await agent_ws_module._handle_usage_report(raw)
    assert fake_csm.forward_usage_report.await_count == 2  # one per active user


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_ios_manager")
async def test_handle_usage_report_ignores_missing_payload(
    fake_csm: MagicMock,
) -> None:
    """Envelopes without payload/content MUST NOT raise — just log + skip."""
    await agent_ws_module._handle_usage_report({"type": "event.usage.report"})
    fake_csm.forward_usage_report.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_ios_manager")
async def test_handle_usage_report_ignores_invalid_payload_types(
    fake_csm: MagicMock,
) -> None:
    """Coercion errors MUST be swallowed (warn + skip), not propagated."""
    raw = {
        "type": "event.usage.report",
        "payload": {
            "five_hour_pct": "not-a-number",  # broken
            "seven_day_pct": 0,
            "five_hour_resets_at": 0,
            "seven_day_resets_at": 0,
            "reported_at": 0,
        },
    }
    await agent_ws_module._handle_usage_report(raw)
    fake_csm.forward_usage_report.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_usage_report_no_active_users_is_noop(
    fake_ios_manager: MagicMock,
    fake_csm: MagicMock,
) -> None:
    """No connected iOS users → no forwarder calls (early return)."""
    fake_ios_manager.get_active_user_ids.return_value = set()
    raw = {
        "type": "event.usage.report",
        "payload": {
            "five_hour_pct": 10,
            "seven_day_pct": 5,
            "five_hour_resets_at": 0,
            "seven_day_resets_at": 0,
            "reported_at": 0,
        },
    }
    await agent_ws_module._handle_usage_report(raw)
    fake_csm.forward_usage_report.assert_not_awaited()


def test_usage_report_message_type_is_registered() -> None:
    """Sanity: USAGE_REPORT enum + value match the bridge wire format suffix."""
    assert MessageType.USAGE_REPORT.value == "usage.report"


# --------------------------------------------------------------------------
# event.session.title — T1.2-fix H-1
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_session_title_resolves_owner_and_forwards(
    fake_csm: MagicMock,
    fake_session_owner: AsyncMock,
) -> None:
    """Happy path: session_id resolves to user → forward_session_title called."""
    sid = uuid4()
    raw = {
        "type": "event.session.title",
        "payload": {
            "session_id": str(sid),
            "ai_title": "Refactor websocket router",
            "generated_at": "2026-05-02T10:00:00+00:00",
        },
    }
    await agent_ws_module._handle_session_title(raw)

    fake_session_owner.assert_awaited_once_with(sid)
    fake_csm.forward_session_title.assert_awaited_once()
    kwargs = fake_csm.forward_session_title.await_args.kwargs
    assert kwargs["user_id"] == "owner-user-id"
    assert kwargs["session_id"] == sid
    assert kwargs["ai_title"] == "Refactor websocket router"
    assert kwargs["generated_at"] == datetime(2026, 5, 2, 10, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_handle_session_title_injects_timestamp_when_omitted(
    fake_csm: MagicMock,
    fake_session_owner: AsyncMock,  # noqa: ARG001
) -> None:
    """Bridge omits ``generated_at`` → handler passes ``None`` so the CSM
    forwarder server-side-injects ``datetime.now(UTC)`` (T1.5 reviewer M3).
    """
    sid = uuid4()
    raw = {
        "type": "event.session.title",
        "payload": {
            "session_id": str(sid),
            "ai_title": "First take",
            # generated_at omitted on purpose
        },
    }
    await agent_ws_module._handle_session_title(raw)

    fake_csm.forward_session_title.assert_awaited_once()
    kwargs = fake_csm.forward_session_title.await_args.kwargs
    # ``None`` → the forwarder fills in datetime.now(UTC) (covered by
    # claude_stream_manager unit tests — here we assert the contract
    # boundary at the routing layer).
    assert kwargs["generated_at"] is None


@pytest.mark.asyncio
async def test_handle_session_title_orphan_session_logs_and_skips(
    fake_csm: MagicMock,
    fake_session_owner: AsyncMock,
) -> None:
    """Unknown session_id → warn (visibility for ops) + no forward call."""
    fake_session_owner.return_value = None
    sid = uuid4()
    raw = {
        "type": "event.session.title",
        "payload": {
            "session_id": str(sid),
            "ai_title": "Orphan-title",
        },
    }
    await agent_ws_module._handle_session_title(raw)

    fake_session_owner.assert_awaited_once_with(sid)
    fake_csm.forward_session_title.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_session_owner")
async def test_handle_session_title_missing_payload_skips(
    fake_csm: MagicMock,
) -> None:
    """No payload/content → warn + skip; no exception propagated."""
    await agent_ws_module._handle_session_title({"type": "event.session.title"})
    fake_csm.forward_session_title.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_session_owner")
async def test_handle_session_title_missing_session_id_skips(
    fake_csm: MagicMock,
) -> None:
    """Payload without session_id → warn + skip."""
    raw = {
        "type": "event.session.title",
        "payload": {"ai_title": "no-sid"},
    }
    await agent_ws_module._handle_session_title(raw)
    fake_csm.forward_session_title.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_session_owner")
async def test_handle_session_title_missing_ai_title_skips(
    fake_csm: MagicMock,
) -> None:
    """Payload without ai_title → warn + skip."""
    raw = {
        "type": "event.session.title",
        "payload": {"session_id": str(uuid4())},
    }
    await agent_ws_module._handle_session_title(raw)
    fake_csm.forward_session_title.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_session_owner")
async def test_handle_session_title_invalid_session_id_skips(
    fake_csm: MagicMock,
) -> None:
    """Non-UUID session_id → warn + skip (no UUID coercion crash)."""
    raw = {
        "type": "event.session.title",
        "payload": {
            "session_id": "not-a-uuid",
            "ai_title": "x",
        },
    }
    await agent_ws_module._handle_session_title(raw)
    fake_csm.forward_session_title.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_session_title_falls_back_to_content_key(
    fake_csm: MagicMock,
    fake_session_owner: AsyncMock,  # noqa: ARG001
) -> None:
    """Legacy bridges that put fields under ``content`` must still work."""
    sid = uuid4()
    raw = {
        "type": "event.session.title",
        "content": {
            "session_id": str(sid),
            "ai_title": "Legacy",
        },
    }
    await agent_ws_module._handle_session_title(raw)
    fake_csm.forward_session_title.assert_awaited_once()


# --------------------------------------------------------------------------
# event.session.pr_opened — T1.2-fix H-1
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_session_pr_opened_resolves_owner_and_forwards(
    fake_csm: MagicMock,
    fake_session_owner: AsyncMock,
) -> None:
    """Happy path: session_id resolves to user → forward_session_pr_opened called."""
    sid = uuid4()
    raw = {
        "type": "event.session.pr_opened",
        "payload": {
            "session_id": str(sid),
            "pr_number": 42,
            "pr_url": "https://github.com/org/repo/pull/42",
            "pr_repository": "org/repo",
            "opened_at": "2026-05-02T11:00:00+00:00",
        },
    }
    await agent_ws_module._handle_session_pr_opened(raw)

    fake_session_owner.assert_awaited_once_with(sid)
    fake_csm.forward_session_pr_opened.assert_awaited_once()
    kwargs = fake_csm.forward_session_pr_opened.await_args.kwargs
    assert kwargs["user_id"] == "owner-user-id"
    assert kwargs["session_id"] == sid
    assert kwargs["pr_number"] == 42
    assert kwargs["pr_url"] == "https://github.com/org/repo/pull/42"
    assert kwargs["pr_repository"] == "org/repo"
    assert kwargs["opened_at"] == datetime(2026, 5, 2, 11, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_handle_session_pr_opened_injects_timestamp_when_omitted(
    fake_csm: MagicMock,
    fake_session_owner: AsyncMock,  # noqa: ARG001
) -> None:
    """Bridge omits ``opened_at`` → handler passes ``None`` so the CSM
    forwarder server-side-injects ``datetime.now(UTC)`` (T1.5 reviewer M3).
    """
    sid = uuid4()
    raw = {
        "type": "event.session.pr_opened",
        "payload": {
            "session_id": str(sid),
            "pr_number": 7,
            "pr_url": "https://github.com/org/repo/pull/7",
            "pr_repository": "org/repo",
        },
    }
    await agent_ws_module._handle_session_pr_opened(raw)

    kwargs = fake_csm.forward_session_pr_opened.await_args.kwargs
    assert kwargs["opened_at"] is None


@pytest.mark.asyncio
async def test_handle_session_pr_opened_orphan_session_logs_and_skips(
    fake_csm: MagicMock,
    fake_session_owner: AsyncMock,
) -> None:
    """Unknown session_id → warn + no forward call (orphan visibility)."""
    fake_session_owner.return_value = None
    raw = {
        "type": "event.session.pr_opened",
        "payload": {
            "session_id": str(uuid4()),
            "pr_number": 1,
            "pr_url": "https://github.com/org/repo/pull/1",
            "pr_repository": "org/repo",
        },
    }
    await agent_ws_module._handle_session_pr_opened(raw)
    fake_csm.forward_session_pr_opened.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_session_owner")
async def test_handle_session_pr_opened_missing_payload_skips(
    fake_csm: MagicMock,
) -> None:
    """No payload/content → warn + skip."""
    await agent_ws_module._handle_session_pr_opened(
        {"type": "event.session.pr_opened"},
    )
    fake_csm.forward_session_pr_opened.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_session_owner")
async def test_handle_session_pr_opened_missing_pr_url_skips(
    fake_csm: MagicMock,
) -> None:
    """Missing pr_url → warn + skip."""
    raw = {
        "type": "event.session.pr_opened",
        "payload": {
            "session_id": str(uuid4()),
            "pr_number": 1,
            "pr_repository": "org/repo",
        },
    }
    await agent_ws_module._handle_session_pr_opened(raw)
    fake_csm.forward_session_pr_opened.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_session_owner")
async def test_handle_session_pr_opened_invalid_pr_number_skips(
    fake_csm: MagicMock,
) -> None:
    """Non-positive / non-numeric pr_number → warn + skip."""
    raw = {
        "type": "event.session.pr_opened",
        "payload": {
            "session_id": str(uuid4()),
            "pr_number": 0,
            "pr_url": "https://github.com/org/repo/pull/0",
            "pr_repository": "org/repo",
        },
    }
    await agent_ws_module._handle_session_pr_opened(raw)
    fake_csm.forward_session_pr_opened.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_session_owner")
async def test_handle_session_pr_opened_invalid_session_id_skips(
    fake_csm: MagicMock,
) -> None:
    """Non-UUID session_id → warn + skip (no UUID coercion crash)."""
    raw = {
        "type": "event.session.pr_opened",
        "payload": {
            "session_id": "not-a-uuid",
            "pr_number": 1,
            "pr_url": "https://github.com/org/repo/pull/1",
            "pr_repository": "org/repo",
        },
    }
    await agent_ws_module._handle_session_pr_opened(raw)
    fake_csm.forward_session_pr_opened.assert_not_awaited()


# --------------------------------------------------------------------------
# _resolve_session_owner — minimal surface, real DB layer is exercised by
# repository tests; here we verify the SessionRepository is called with
# the correct UUID and that the user_id is stringified.
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_session_owner_returns_stringified_user_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the row exists, the user_id is returned as ``str(uuid)``."""
    sid = uuid4()
    owner_uuid = uuid4()

    fake_session = AsyncMock()
    fake_session.__aenter__.return_value = fake_session
    fake_session.__aexit__.return_value = None
    monkeypatch.setattr(
        agent_ws_module,
        "async_session_factory",
        lambda: fake_session,
    )

    fake_repo = AsyncMock()
    fake_repo.get_by_id = AsyncMock(
        return_value=SimpleNamespace(user_id=owner_uuid),
    )
    monkeypatch.setattr(
        "app.repositories.session_repo.SessionRepository",
        lambda _session: fake_repo,
    )

    result = await agent_ws_module._resolve_session_owner(sid)
    assert result == str(owner_uuid)
    fake_repo.get_by_id.assert_awaited_once_with(sid)


@pytest.mark.asyncio
async def test_resolve_session_owner_returns_none_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing row → ``None`` (caller logs as orphan)."""
    sid = uuid4()

    fake_session = AsyncMock()
    fake_session.__aenter__.return_value = fake_session
    fake_session.__aexit__.return_value = None
    monkeypatch.setattr(
        agent_ws_module,
        "async_session_factory",
        lambda: fake_session,
    )

    fake_repo = AsyncMock()
    fake_repo.get_by_id = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "app.repositories.session_repo.SessionRepository",
        lambda _session: fake_repo,
    )

    result = await agent_ws_module._resolve_session_owner(sid)
    assert result is None


def test_session_title_message_type_is_registered() -> None:
    """Sanity: SESSION_TITLE enum + value match the bridge wire format suffix."""
    assert MessageType.SESSION_TITLE.value == "session.title"


def test_session_pr_opened_message_type_is_registered() -> None:
    """Sanity: SESSION_PR_OPENED enum + value match the bridge wire format."""
    assert MessageType.SESSION_PR_OPENED.value == "session.pr_opened"


# --------------------------------------------------------------------------
# T2.2-fix M1: storage observability metric emission
# --------------------------------------------------------------------------
#
# These tests assert the wiring of ``storage_events_processed_total`` +
# ``storage_watcher_lag_seconds`` (Doc 10 §7.3) for each of the three
# storage handlers (_handle_usage_report, _handle_session_title,
# _handle_session_pr_opened). They re-render ``/metrics`` (via
# ``render_metrics``) and parse it with the official Prometheus parser so
# we exercise the same path as the scrape endpoint.


def _samples_for(body: str, metric_name: str) -> list:  # type: ignore[type-arg]
    """Return all samples whose name matches ``metric_name``."""
    out: list = []  # type: ignore[type-arg]
    for fam in text_string_to_metric_families(body):
        for sample in fam.samples:
            if sample.name == metric_name:
                out.append(sample)
    return out


def _counter_value(metric_name: str, labels: dict[str, str]) -> float:
    """Return the value of a counter sample matching ``labels`` (or 0.0)."""
    body, _ = _metrics.render_metrics()
    for sample in _samples_for(body.decode(), metric_name):
        if all(sample.labels.get(k) == v for k, v in labels.items()):
            return float(sample.value)
    return 0.0


@pytest.fixture
def _isolated_storage_metrics() -> object:
    """Clear storage metric families so per-test assertions start at 0."""
    _metrics.storage_events_processed_total.clear()
    _metrics.storage_watcher_lag_seconds.clear()
    yield
    _metrics.storage_events_processed_total.clear()
    _metrics.storage_watcher_lag_seconds.clear()


@pytest.mark.asyncio
@pytest.mark.usefixtures("_isolated_storage_metrics")
async def test_session_title_emits_storage_metrics(
    fake_csm: MagicMock,  # noqa: ARG001
    fake_session_owner: AsyncMock,  # noqa: ARG001
) -> None:
    """ai-title forward bumps the type=ai-title counter + observes lag."""
    sid = uuid4()
    # Generated 30s in the past so we observe a positive lag bucket.
    generated_at = datetime.now(UTC).replace(microsecond=0)
    raw = {
        "type": "event.session.title",
        "payload": {
            "session_id": str(sid),
            "ai_title": "x",
            "generated_at": generated_at.isoformat(),
        },
    }
    await agent_ws_module._handle_session_title(raw, "mac-01")

    # Counter incremented exactly once with type=ai-title + bridge_id=mac-01.
    assert (
        _counter_value(
            "storage_events_processed_total",
            {"type": "ai-title", "bridge_id": "mac-01"},
        )
        == 1.0
    )

    # Histogram observed at least one sample (lag clamped >= 0).
    body, _ = _metrics.render_metrics()
    count_samples = _samples_for(body.decode(), "storage_watcher_lag_seconds_count")
    matching = [s for s in count_samples if s.labels.get("bridge_id") == "mac-01"]
    assert matching, "expected storage_watcher_lag_seconds count for mac-01"
    assert matching[0].value == 1


@pytest.mark.asyncio
@pytest.mark.usefixtures("_isolated_storage_metrics")
async def test_session_title_skips_lag_when_generated_at_omitted(
    fake_csm: MagicMock,  # noqa: ARG001
    fake_session_owner: AsyncMock,  # noqa: ARG001
) -> None:
    """No bridge-side timestamp → counter still bumps, lag is NOT observed.

    Observing 0s when the CSM forwarder server-side-injected ``now()``
    would skew the histogram baseline; we explicitly skip the observe.
    """
    raw = {
        "type": "event.session.title",
        "payload": {
            "session_id": str(uuid4()),
            "ai_title": "x",
            # generated_at omitted on purpose
        },
    }
    await agent_ws_module._handle_session_title(raw, "mac-01")

    # Counter still bumps (the event WAS processed).
    assert (
        _counter_value(
            "storage_events_processed_total",
            {"type": "ai-title", "bridge_id": "mac-01"},
        )
        == 1.0
    )

    # But no histogram sample.
    body, _ = _metrics.render_metrics()
    count_samples = _samples_for(body.decode(), "storage_watcher_lag_seconds_count")
    matching = [s for s in count_samples if s.labels.get("bridge_id") == "mac-01"]
    assert not matching


@pytest.mark.asyncio
@pytest.mark.usefixtures("_isolated_storage_metrics")
async def test_session_title_metrics_use_unknown_when_bridge_id_none(
    fake_csm: MagicMock,  # noqa: ARG001
    fake_session_owner: AsyncMock,  # noqa: ARG001
) -> None:
    """Bridge that skipped registration → label falls back to "unknown"."""
    raw = {
        "type": "event.session.title",
        "payload": {
            "session_id": str(uuid4()),
            "ai_title": "x",
        },
    }
    # Explicitly omit bridge_id (default None).
    await agent_ws_module._handle_session_title(raw)
    assert (
        _counter_value(
            "storage_events_processed_total",
            {"type": "ai-title", "bridge_id": "unknown"},
        )
        == 1.0
    )


@pytest.mark.asyncio
@pytest.mark.usefixtures("_isolated_storage_metrics")
async def test_session_title_orphan_does_not_emit_metrics(
    fake_csm: MagicMock,  # noqa: ARG001
    fake_session_owner: AsyncMock,
) -> None:
    """Unknown session → metric MUST NOT bump (event wasn't fully processed)."""
    fake_session_owner.return_value = None
    raw = {
        "type": "event.session.title",
        "payload": {
            "session_id": str(uuid4()),
            "ai_title": "orphan",
            "generated_at": datetime.now(UTC).isoformat(),
        },
    }
    await agent_ws_module._handle_session_title(raw, "mac-01")
    assert (
        _counter_value(
            "storage_events_processed_total",
            {"type": "ai-title", "bridge_id": "mac-01"},
        )
        == 0.0
    )


@pytest.mark.asyncio
@pytest.mark.usefixtures("_isolated_storage_metrics")
async def test_session_pr_opened_emits_storage_metrics(
    fake_csm: MagicMock,  # noqa: ARG001
    fake_session_owner: AsyncMock,  # noqa: ARG001
) -> None:
    """pr-link forward bumps the type=pr-link counter + observes lag."""
    opened_at = datetime.now(UTC).replace(microsecond=0)
    raw = {
        "type": "event.session.pr_opened",
        "payload": {
            "session_id": str(uuid4()),
            "pr_number": 42,
            "pr_url": "https://github.com/o/r/pull/42",
            "pr_repository": "o/r",
            "opened_at": opened_at.isoformat(),
        },
    }
    await agent_ws_module._handle_session_pr_opened(raw, "mac-02")

    assert (
        _counter_value(
            "storage_events_processed_total",
            {"type": "pr-link", "bridge_id": "mac-02"},
        )
        == 1.0
    )
    body, _ = _metrics.render_metrics()
    matching = [
        s
        for s in _samples_for(body.decode(), "storage_watcher_lag_seconds_count")
        if s.labels.get("bridge_id") == "mac-02"
    ]
    assert matching
    assert matching[0].value == 1


@pytest.mark.asyncio
@pytest.mark.usefixtures("_isolated_storage_metrics", "fake_ios_manager")
async def test_usage_report_emits_storage_metrics(
    fake_csm: MagicMock,  # noqa: ARG001
) -> None:
    """usage-report forward bumps the type=usage-report counter + lag."""
    # Use a unix epoch slightly in the past so lag is positive.
    reported_at = int(datetime.now(UTC).timestamp()) - 10
    raw = {
        "type": "event.usage.report",
        "payload": {
            "five_hour_pct": 73,
            "seven_day_pct": 41,
            "five_hour_resets_at": 1735689600,
            "seven_day_resets_at": 1736294400,
            "reported_at": reported_at,
        },
    }
    await agent_ws_module._handle_usage_report(raw, "mac-03")

    assert (
        _counter_value(
            "storage_events_processed_total",
            {"type": "usage-report", "bridge_id": "mac-03"},
        )
        == 1.0
    )
    body, _ = _metrics.render_metrics()
    matching = [
        s
        for s in _samples_for(body.decode(), "storage_watcher_lag_seconds_count")
        if s.labels.get("bridge_id") == "mac-03"
    ]
    assert matching
    assert matching[0].value == 1


@pytest.mark.asyncio
@pytest.mark.usefixtures("_isolated_storage_metrics", "fake_ios_manager")
async def test_usage_report_skips_lag_when_reported_at_zero(
    fake_csm: MagicMock,  # noqa: ARG001
) -> None:
    """``reported_at = 0`` → counter still bumps, lag NOT observed.

    A zero unix epoch is the bridge's "unset" sentinel; observing the
    1970→now delta would saturate every histogram bucket.
    """
    raw = {
        "type": "event.usage.report",
        "payload": {
            "five_hour_pct": 5,
            "seven_day_pct": 2,
            "five_hour_resets_at": 0,
            "seven_day_resets_at": 0,
            "reported_at": 0,
        },
    }
    await agent_ws_module._handle_usage_report(raw, "mac-04")

    assert (
        _counter_value(
            "storage_events_processed_total",
            {"type": "usage-report", "bridge_id": "mac-04"},
        )
        == 1.0
    )
    body, _ = _metrics.render_metrics()
    matching = [
        s
        for s in _samples_for(body.decode(), "storage_watcher_lag_seconds_count")
        if s.labels.get("bridge_id") == "mac-04"
    ]
    assert not matching
