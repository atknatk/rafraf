"""Unit tests for the Prometheus metrics surface (T2.2).

Covers:
* /metrics endpoint returns 200 + valid Prometheus exposition format
* Counter / gauge / histogram emit sites work end-to-end (parsed back
  via :func:`prometheus_client.parser.text_string_to_metric_families`)
* WS connection-manager gauge incr/decr lifecycle
* Cumulative claude cost counter increments via the runner finally-block
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from prometheus_client.parser import text_string_to_metric_families
from starlette.websockets import WebSocketState

from app.core import metrics as _metrics
from app.core.websocket import ConnectionManager

# ---------------------------------------------------------------------------
# Fixture: clean registry between tests so counter values don't bleed across
# test functions. We _reset_ the underlying ``_value`` of each metric the
# tests touch rather than rebuilding the registry — Counter/Gauge/Histogram
# instances are module-level and re-creating them would invalidate every
# import-time reference held by the production code.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_metrics() -> Iterator[None]:
    """Snapshot + restore label values so tests don't pollute each other."""
    # Clear all per-label child counters so each test starts from a known
    # state. ``_metrics`` exposes only top-level metric families; calling
    # ``.clear()`` on each removes every previously-emitted labelset.
    families = (
        _metrics.claude_total_cost_usd_total,
        _metrics.subagent_spawned_total,
        _metrics.claude_rate_limit_hits_total,
        _metrics.apns_delivery_success_total,
        _metrics.apns_delivery_failure_total,
        _metrics.storage_events_processed_total,
        _metrics.claude_usage_report_total,
        _metrics.claude_subprocess_count,
        _metrics.ws_connections_active,
        _metrics.claude_5h_usage_pct,
        _metrics.claude_7d_usage_pct,
        _metrics.claude_usage_report_age_seconds,
        _metrics.claude_subprocess_duration_seconds,
        _metrics.storage_watcher_lag_seconds,
    )
    for fam in families:
        fam.clear()
    yield
    for fam in families:
        fam.clear()


# ---------------------------------------------------------------------------
# /metrics endpoint
# ---------------------------------------------------------------------------


def test_metrics_endpoint_returns_200_with_prometheus_text_format() -> None:
    """GET /metrics must serve a valid Prometheus exposition body."""
    from app.main import app

    with TestClient(app) as client:
        response = client.get("/metrics")

    assert response.status_code == 200
    content_type = response.headers.get("content-type", "")
    # The official content-type is "text/plain; version=0.0.4" (or
    # ``CONTENT_TYPE_LATEST``); the exact suffix changes between
    # client versions, so we only assert the prefix.
    assert content_type.startswith("text/plain")
    # Body must parse cleanly as Prometheus exposition.
    families = list(text_string_to_metric_families(response.text))
    family_names = {fam.name for fam in families}
    # Spot-check a sample from each metric category.
    assert "claude_total_cost_usd" in family_names  # counter (suffix stripped)
    assert "subagent_spawned" in family_names
    assert "ws_connections_active" in family_names  # gauge
    assert "claude_subprocess_duration_seconds" in family_names  # histogram


def test_metrics_endpoint_excluded_from_openapi_schema() -> None:
    """/metrics must not leak into the iOS-facing OpenAPI doc."""
    from app.main import app

    with TestClient(app) as client:
        schema = client.get("/openapi.json").json()

    assert "/metrics" not in schema.get("paths", {})


# ---------------------------------------------------------------------------
# Counter emission via direct calls (mocking the dispatch layer)
# ---------------------------------------------------------------------------


def test_subagent_spawned_counter_increments_with_status_label() -> None:
    """Each call to ``.labels(...).inc()`` must surface in the export."""
    _metrics.subagent_spawned_total.labels(bridge_id="mac-01", status="started").inc()
    _metrics.subagent_spawned_total.labels(bridge_id="mac-01", status="completed").inc()
    _metrics.subagent_spawned_total.labels(bridge_id="mac-01", status="failed").inc(2)

    body, _ = _metrics.render_metrics()
    samples = _samples_for(body.decode(), "subagent_spawned_total")
    by_status = {s.labels["status"]: s.value for s in samples}
    assert by_status["started"] == 1
    assert by_status["completed"] == 1
    assert by_status["failed"] == 2


def test_claude_total_cost_counter_accumulates() -> None:
    """Repeated cost increments must accumulate per (bridge, session)."""
    _metrics.claude_total_cost_usd_total.labels(bridge_id="mac-01", session_id="sess-A").inc(0.123)
    _metrics.claude_total_cost_usd_total.labels(bridge_id="mac-01", session_id="sess-A").inc(0.456)
    _metrics.claude_total_cost_usd_total.labels(bridge_id="mac-01", session_id="sess-B").inc(0.001)

    body, _ = _metrics.render_metrics()
    samples = _samples_for(body.decode(), "claude_total_cost_usd_total")
    by_session = {s.labels["session_id"]: s.value for s in samples}
    assert pytest.approx(by_session["sess-A"], rel=1e-6) == 0.579
    assert pytest.approx(by_session["sess-B"], rel=1e-6) == 0.001


def test_apns_delivery_counters_track_success_and_failure() -> None:
    """APNs counters are partitioned by token_type."""
    _metrics.apns_delivery_success_total.labels(token_type="sandbox").inc(3)
    _metrics.apns_delivery_failure_total.labels(token_type="sandbox").inc()
    _metrics.apns_delivery_failure_total.labels(token_type="production").inc(2)

    body, _ = _metrics.render_metrics()
    success = {
        s.labels["token_type"]: s.value
        for s in _samples_for(body.decode(), "apns_delivery_success_total")
    }
    failure = {
        s.labels["token_type"]: s.value
        for s in _samples_for(body.decode(), "apns_delivery_failure_total")
    }
    assert success["sandbox"] == 3
    assert failure["sandbox"] == 1
    assert failure["production"] == 2


# ---------------------------------------------------------------------------
# Gauge lifecycle
# ---------------------------------------------------------------------------


async def test_ws_connections_active_gauge_lifecycle() -> None:
    """ConnectionManager must incr/decr the ws_connections_active gauge."""
    manager = ConnectionManager(heartbeat_interval=30, heartbeat_timeout=10, kind="ios")
    ws = AsyncMock()
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    ws.client_state = WebSocketState.CONNECTED

    initial = _gauge_value("ws_connections_active", labels={"kind": "ios"})
    assert initial == 0  # cleared by fixture

    cid = await manager.connect(websocket=ws, user_id="u-1", session_id="s-1")
    assert _gauge_value("ws_connections_active", labels={"kind": "ios"}) == 1

    cid2 = await manager.connect(websocket=ws, user_id="u-2", session_id="s-2")
    assert _gauge_value("ws_connections_active", labels={"kind": "ios"}) == 2

    await manager.disconnect(cid)
    assert _gauge_value("ws_connections_active", labels={"kind": "ios"}) == 1

    await manager.disconnect(cid2)
    assert _gauge_value("ws_connections_active", labels={"kind": "ios"}) == 0


def test_claude_subprocess_count_gauge_set_from_heartbeat() -> None:
    """Setting the gauge to a snapshot value must be reflected in /metrics."""
    _metrics.claude_subprocess_count.labels(bridge_id="mac-01").set(3)
    _metrics.claude_subprocess_count.labels(bridge_id="mac-02").set(0)

    snap_one = _gauge_value("claude_subprocess_count", labels={"bridge_id": "mac-01"})
    snap_two = _gauge_value("claude_subprocess_count", labels={"bridge_id": "mac-02"})
    assert snap_one == 3
    assert snap_two == 0


def test_usage_pct_gauges_per_user() -> None:
    """5h/7d usage pct gauges must be observable per user_id."""
    _metrics.claude_5h_usage_pct.labels(user_id="user-A").set(42)
    _metrics.claude_7d_usage_pct.labels(user_id="user-A").set(73)
    _metrics.claude_5h_usage_pct.labels(user_id="user-B").set(10)

    body, _ = _metrics.render_metrics()
    five = {
        s.labels["user_id"]: s.value for s in _samples_for(body.decode(), "claude_5h_usage_pct")
    }
    seven = {
        s.labels["user_id"]: s.value for s in _samples_for(body.decode(), "claude_7d_usage_pct")
    }
    assert five == {"user-A": 42, "user-B": 10}
    assert seven == {"user-A": 73}


# ---------------------------------------------------------------------------
# Histogram observation
# ---------------------------------------------------------------------------


def test_claude_subprocess_duration_histogram_records_observation() -> None:
    """observe() should bump the appropriate bucket + the _count + _sum."""
    _metrics.claude_subprocess_duration_seconds.labels(bridge_id="mac-01").observe(2.5)
    _metrics.claude_subprocess_duration_seconds.labels(bridge_id="mac-01").observe(45.0)

    body, _ = _metrics.render_metrics()
    text = body.decode()
    # _count must be 2.
    count_samples = _samples_for(text, "claude_subprocess_duration_seconds_count")
    assert count_samples
    assert count_samples[0].value == 2
    # _sum must be 47.5 (within float tolerance).
    sum_samples = _samples_for(text, "claude_subprocess_duration_seconds_sum")
    assert sum_samples
    assert pytest.approx(sum_samples[0].value, rel=1e-6) == 47.5


def test_storage_watcher_lag_histogram_uses_configured_buckets() -> None:
    """The histogram must expose the explicit buckets from metrics.py."""
    _metrics.storage_watcher_lag_seconds.labels(bridge_id="mac-01").observe(0.07)

    body, _ = _metrics.render_metrics()
    bucket_samples = _samples_for(body.decode(), "storage_watcher_lag_seconds_bucket")
    upper_bounds = {
        float(s.labels["le"]) for s in bucket_samples if s.labels.get("bridge_id") == "mac-01"
    }
    # Check the canonical buckets we configured (Doc 10 §7.3 + +Inf).
    expected = {0.05, 0.1, 0.5, 1.0, 5.0}
    assert expected.issubset(upper_bounds)


# ---------------------------------------------------------------------------
# Integration: claude_code_runner finally-block emission
# ---------------------------------------------------------------------------


async def test_runner_emits_cost_counter_on_completion() -> None:
    """ClaudeCodeRunner should bump cost + duration after a streamed result."""
    from app.orchestrator.claude_code_runner import ClaudeCodeRunner

    bridges = MagicMock()
    bridges.get_connection_id = MagicMock(return_value="conn-1")
    bridges.find_online_agent_with_capability = MagicMock(return_value="mac-01")
    queue: AsyncMock = AsyncMock()
    bridges.register_subscriber = MagicMock(return_value=queue)
    bridges.unregister_subscriber = MagicMock()
    bridges.send_to_bridge = AsyncMock(return_value=True)

    async def _fake_stream(**_kwargs: object):  # type: ignore[no-untyped-def]
        # Yield only the terminal result envelope.
        yield {
            "type": "event.session.result",
            "correlation_id": "rpc-1",
            "payload": {
                "duration_ms": 4200,
                "result": "done",
                "total_cost_usd": 0.03,
            },
        }

    bridges.stream_events = _fake_stream  # type: ignore[assignment]

    runner = ClaudeCodeRunner(bridge_registry=bridges)
    result = await runner.run(
        prompt="hello",
        bridge_id="mac-01",
    )

    assert result.total_cost_usd == 0.03
    cost = _gauge_value(
        "claude_total_cost_usd_total",
        labels={"bridge_id": "mac-01", "session_id": "unknown"},
    )
    assert pytest.approx(cost, rel=1e-6) == 0.03
    duration_count = _gauge_value(
        "claude_subprocess_duration_seconds_count",
        labels={"bridge_id": "mac-01"},
    )
    assert duration_count == 1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _samples_for(body: str, metric_name: str) -> list:  # type: ignore[type-arg]
    """Pull every sample whose name matches ``metric_name`` from a body."""
    out: list = []  # type: ignore[type-arg]
    for fam in text_string_to_metric_families(body):
        for sample in fam.samples:
            if sample.name == metric_name:
                out.append(sample)
    return out


def _gauge_value(metric_name: str, *, labels: dict[str, str]) -> float:
    """Look up a single gauge / counter value by name + labelset."""
    body, _ = _metrics.render_metrics()
    for sample in _samples_for(body.decode(), metric_name):
        if all(sample.labels.get(k) == v for k, v in labels.items()):
            return float(sample.value)
    return 0.0


# ``time`` import retained so future tests can monkey-patch durations
# without re-importing.
_ = time
