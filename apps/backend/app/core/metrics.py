"""Prometheus metric definitions for the RafRaf backend (T2.2).

The metric catalogue is sourced from ``docs/10_Production_Pivot_Spec.md``
§7.3. We use :mod:`prometheus_client` directly (rather than
``prometheus-fastapi-instrumentator``) because:

* The bridge fan-out pattern means most metric increments happen in
  service code (claude runner, bridge registry, claude stream manager,
  apns client) — *not* on a single FastAPI request lifecycle. The
  instrumentator's auto-wired `/metrics` + request-level counters would
  add a layer that doesn't help us, and we'd still need to define and
  emit every business metric manually.
* A separate registry keeps metric names + emit sites in one place
  (this module), which makes review + grep significantly easier.
* Keeping the surface explicit also lets unit tests reset / inspect
  individual metrics without monkey-patching middleware.

Each metric is module-level so call sites import the symbol directly:

    from app.core.metrics import claude_total_cost_usd_total

    claude_total_cost_usd_total.labels(
        bridge_id=host_id, session_id=session_id
    ).inc(cost_usd)

Public surface:

* :data:`REGISTRY` — :class:`CollectorRegistry` Prometheus uses to render
  ``/metrics``. The default global registry is intentionally *not* used
  so test runs can build a clean registry fixture.
* :func:`render_metrics` — produces the ``text/plain; version=0.0.4``
  body the ``/metrics`` route returns.
* The metric instances themselves (counters / gauges / histograms).

The catalogue intentionally mirrors the bridge ``expvar`` names where
they overlap (Doc 11 §9 → Doc 10 §7.3) so cross-component dashboards can
share queries.
"""

from __future__ import annotations

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

# Dedicated registry keeps backend-emitted metrics isolated from any
# third-party auto-collectors that might register against the global
# default registry (e.g. test harnesses, opentelemetry shims). The
# `/metrics` route returns this registry's snapshot.
REGISTRY: CollectorRegistry = CollectorRegistry(auto_describe=True)


# ---------------------------------------------------------------------------
# Counters
# ---------------------------------------------------------------------------

claude_total_cost_usd_total: Counter = Counter(
    "claude_total_cost_usd_total",
    "Cumulative claude API cost in USD across all sessions.",
    labelnames=("bridge_id", "session_id"),
    registry=REGISTRY,
)

subagent_spawned_total: Counter = Counter(
    "subagent_spawned_total",
    "Subagents (Task tool) the backend observed.",
    labelnames=("bridge_id", "status"),
    registry=REGISTRY,
)

claude_rate_limit_hits_total: Counter = Counter(
    "claude_rate_limit_hits_total",
    "Rate-limit events surfaced by claude.",
    labelnames=("bridge_id", "rate_limit_type"),
    registry=REGISTRY,
)

apns_delivery_success_total: Counter = Counter(
    "apns_delivery_success_total",
    "APNs push notifications successfully accepted by Apple.",
    labelnames=("token_type",),
    registry=REGISTRY,
)

apns_delivery_failure_total: Counter = Counter(
    "apns_delivery_failure_total",
    "APNs push notifications that Apple rejected or that failed to send.",
    labelnames=("token_type",),
    registry=REGISTRY,
)

storage_events_processed_total: Counter = Counter(
    "storage_events_processed_total",
    "Storage events (ai-title / pr-link / attachment) forwarded.",
    labelnames=("type", "bridge_id"),
    registry=REGISTRY,
)

claude_usage_report_total: Counter = Counter(
    "claude_usage_report_total",
    "usage.report envelopes the backend forwarded to iOS clients.",
    labelnames=("bridge_id",),
    registry=REGISTRY,
)


# ---------------------------------------------------------------------------
# Gauges
# ---------------------------------------------------------------------------

claude_subprocess_count: Gauge = Gauge(
    "claude_subprocess_count",
    "Active claude subprocesses (per bridge, snapshot).",
    labelnames=("bridge_id",),
    registry=REGISTRY,
)

ws_connections_active: Gauge = Gauge(
    "ws_connections_active",
    "Active WebSocket connections, partitioned by client kind.",
    labelnames=("kind",),
    registry=REGISTRY,
)

claude_5h_usage_pct: Gauge = Gauge(
    "claude_5h_usage_pct",
    "Most recently reported 5-hour claude subscription usage percentage.",
    labelnames=("user_id",),
    registry=REGISTRY,
)

claude_7d_usage_pct: Gauge = Gauge(
    "claude_7d_usage_pct",
    "Most recently reported 7-day claude subscription usage percentage.",
    labelnames=("user_id",),
    registry=REGISTRY,
)

claude_usage_report_age_seconds: Gauge = Gauge(
    "claude_usage_report_age_seconds",
    "Seconds since the last usage.report was forwarded for the user.",
    labelnames=("user_id",),
    registry=REGISTRY,
)


# ---------------------------------------------------------------------------
# Histograms
# ---------------------------------------------------------------------------

# Buckets chosen per Doc 10 §7.3 — covers sub-second tool calls all the
# way up to long-running multi-turn sessions (10 minutes).
_CLAUDE_DURATION_BUCKETS: tuple[float, ...] = (
    0.5,
    1.0,
    2.0,
    5.0,
    10.0,
    30.0,
    60.0,
    300.0,
    600.0,
)

claude_subprocess_duration_seconds: Histogram = Histogram(
    "claude_subprocess_duration_seconds",
    "Wall-clock duration of a claude subprocess run.",
    labelnames=("bridge_id",),
    buckets=_CLAUDE_DURATION_BUCKETS,
    registry=REGISTRY,
)

# Storage watcher lag is sub-second on the happy path; a 5s observation
# already indicates fsnotify backpressure or a slow sink.
_STORAGE_LAG_BUCKETS: tuple[float, ...] = (0.05, 0.1, 0.5, 1.0, 5.0)

storage_watcher_lag_seconds: Histogram = Histogram(
    "storage_watcher_lag_seconds",
    "Observed lag between the storage event timestamp and processing time.",
    labelnames=("bridge_id",),
    buckets=_STORAGE_LAG_BUCKETS,
    registry=REGISTRY,
)


# ---------------------------------------------------------------------------
# Render helper
# ---------------------------------------------------------------------------


def render_metrics() -> tuple[bytes, str]:
    """Return ``(body, content_type)`` ready to ship from FastAPI.

    Wrapping :func:`prometheus_client.generate_latest` here lets the
    route handler stay a one-liner and centralises the registry choice
    so we never accidentally render the global default.
    """
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST


__all__ = [
    "CONTENT_TYPE_LATEST",
    "REGISTRY",
    "apns_delivery_failure_total",
    "apns_delivery_success_total",
    "claude_5h_usage_pct",
    "claude_7d_usage_pct",
    "claude_rate_limit_hits_total",
    "claude_subprocess_count",
    "claude_subprocess_duration_seconds",
    "claude_total_cost_usd_total",
    "claude_usage_report_age_seconds",
    "claude_usage_report_total",
    "render_metrics",
    "storage_events_processed_total",
    "storage_watcher_lag_seconds",
    "subagent_spawned_total",
    "ws_connections_active",
]
