"""Unit tests for rate limiting middleware."""

import json
import time

import pytest
import structlog
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.middleware.rate_limit import (
    RateLimitMiddleware,
    RateLimitStore,
    _classify_endpoint,
)
from app.core.metrics import backend_rate_limit_hits_total


class TestRateLimitStore:
    """Tests for the in-memory RateLimitStore."""

    def test_allows_requests_under_limit(self) -> None:
        """Requests under the limit should not be rate limited."""
        store = RateLimitStore()
        for _ in range(5):
            assert store.is_rate_limited("ip:1.2.3.4", max_requests=10, window_seconds=60) is False

    def test_blocks_requests_at_limit(self) -> None:
        """Requests at or over the limit should be rate limited."""
        store = RateLimitStore()
        for _ in range(10):
            store.is_rate_limited("ip:1.2.3.4", max_requests=10, window_seconds=60)
        assert store.is_rate_limited("ip:1.2.3.4", max_requests=10, window_seconds=60) is True

    def test_different_keys_tracked_independently(self) -> None:
        """Rate limits should be tracked per key."""
        store = RateLimitStore()
        for _ in range(10):
            store.is_rate_limited("ip:1.2.3.4", max_requests=10, window_seconds=60)
        # Different key should still be allowed
        assert store.is_rate_limited("ip:5.6.7.8", max_requests=10, window_seconds=60) is False

    def test_expired_entries_cleaned_up(self) -> None:
        """Expired entries should be removed from tracking."""
        store = RateLimitStore()
        # Use a very short window
        for _ in range(5):
            store.is_rate_limited("ip:1.2.3.4", max_requests=5, window_seconds=0)
        # After expiry, should be allowed again (window=0 means all entries expire)
        assert store.is_rate_limited("ip:1.2.3.4", max_requests=5, window_seconds=0) is False

    def test_exact_limit_boundary(self) -> None:
        """At exactly max_requests, next request should be blocked."""
        store = RateLimitStore()
        results = []
        for _ in range(11):
            results.append(store.is_rate_limited("ip:test", max_requests=10, window_seconds=60))
        # First 10 should pass, 11th should be blocked
        assert results[:10] == [False] * 10
        assert results[10] is True


# ---------------------------------------------------------------------------
# T2.4 — Endpoint classifier (low-cardinality Prometheus label).
# ---------------------------------------------------------------------------


class TestClassifyEndpoint:
    """``_classify_endpoint`` collapses paths to a stable label value."""

    def test_api_v1_classified_to_three_segments(self) -> None:
        assert _classify_endpoint("/api/v1/auth/login") == "/api/v1/auth"
        assert _classify_endpoint("/api/v1/auth/refresh") == "/api/v1/auth"

    def test_unknown_returns_root_segment(self) -> None:
        assert _classify_endpoint("/healthz") == "/healthz"

    def test_empty_returns_unknown(self) -> None:
        assert _classify_endpoint("") == "unknown"
        assert _classify_endpoint("/") == "unknown"


# ---------------------------------------------------------------------------
# T2.4 — Middleware emission, Retry-After header, JSON body shape.
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_store() -> RateLimitStore:
    """Per-test in-memory store so tests don't share counters."""
    return RateLimitStore()


def _build_app(store: RateLimitStore) -> FastAPI:
    """Build a minimal FastAPI app wired only with RateLimitMiddleware."""
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, rate_limit_store=store)

    @app.post("/api/v1/auth/login")
    def _login() -> dict[str, str]:
        return {"ok": "yes"}

    return app


class TestMiddlewareEmission:
    """T2.4 — middleware MUST emit counter, Retry-After header, JSON body."""

    def test_429_response_includes_retry_after_header(
        self,
        isolated_store: RateLimitStore,
    ) -> None:
        app = _build_app(isolated_store)
        client = TestClient(app)

        # Settings cap at 10/min by default; saturate then trip.
        for _ in range(10):
            client.post("/api/v1/auth/login", json={})

        resp = client.post("/api/v1/auth/login", json={})
        assert resp.status_code == 429
        assert resp.headers.get("Retry-After") is not None
        assert int(resp.headers["Retry-After"]) > 0

    def test_429_body_matches_rate_limit_info_shape(
        self,
        isolated_store: RateLimitStore,
    ) -> None:
        app = _build_app(isolated_store)
        client = TestClient(app)
        for _ in range(10):
            client.post("/api/v1/auth/login", json={})
        resp = client.post("/api/v1/auth/login", json={})
        assert resp.status_code == 429
        body = resp.json()
        assert body["detail"]
        rate_limit = body["rate_limit"]
        assert rate_limit["status"] == "exceeded"
        assert rate_limit["rate_limit_type"] == "backend_per_ip"
        assert rate_limit["source"] == "api_middleware"
        assert isinstance(rate_limit["resets_at"], int)
        assert rate_limit["resets_at"] > int(time.time())
        assert isinstance(rate_limit["retry_after_seconds"], int)
        assert rate_limit["retry_after_seconds"] > 0

    def test_429_increments_backend_rate_limit_counter(
        self,
        isolated_store: RateLimitStore,
    ) -> None:
        sample = backend_rate_limit_hits_total.labels(
            endpoint="/api/v1/auth",
            source="api_middleware",
        )
        before = sample._value.get()  # type: ignore[attr-defined]

        app = _build_app(isolated_store)
        client = TestClient(app)
        for _ in range(10):
            client.post("/api/v1/auth/login", json={})
        resp = client.post("/api/v1/auth/login", json={})
        assert resp.status_code == 429

        after = sample._value.get()  # type: ignore[attr-defined]
        assert after - before == 1.0

    def test_non_auth_path_bypasses_throttler(
        self,
        isolated_store: RateLimitStore,
    ) -> None:
        app = _build_app(isolated_store)

        @app.get("/api/v1/projects")
        def _projects() -> dict[str, str]:
            return {"ok": "yes"}

        client = TestClient(app)
        # 50 requests on a non-auth path MUST NOT trip.
        for _ in range(50):
            r = client.get("/api/v1/projects")
            assert r.status_code == 200

    def test_429_body_is_parseable_as_json(
        self,
        isolated_store: RateLimitStore,
    ) -> None:
        """iOS decoder consumes the body as JSON — it MUST round-trip cleanly."""
        app = _build_app(isolated_store)
        client = TestClient(app)
        for _ in range(10):
            client.post("/api/v1/auth/login", json={})
        resp = client.post("/api/v1/auth/login", json={})
        # raw bytes → JSON parse must succeed without exceptions
        parsed = json.loads(resp.content)
        assert parsed["rate_limit"]["status"] == "exceeded"


# ---------------------------------------------------------------------------
# T2.4 L2 — sliding-window Retry-After (no longer fixed at 60s).
# ---------------------------------------------------------------------------


class TestSlidingWindowRetryAfter:
    """``seconds_until_next_slot`` MUST reflect the actual cool-down time
    remaining for the oldest in-window entry, not a fixed full-window
    value. Validates the L2 deferral resolution."""

    def test_returns_short_window_when_oldest_entry_is_aging(self) -> None:
        """If the oldest entry is already 55s old in a 60s window, the
        next slot opens in ~5s — the hint MUST reflect that."""
        store = RateLimitStore()
        # Saturate the limit with timestamps backdated ~55s.
        backdated_now = time.monotonic() - 55
        store._requests["sliding:1"] = [backdated_now] * 10  # noqa: SLF001
        secs = store.seconds_until_next_slot(key="sliding:1", max_requests=10, window_seconds=60)
        # Expect ~5s remaining — accept 4..7 to absorb monotonic jitter.
        assert 4 <= secs <= 7, f"sliding hint should be ~5s, got {secs}"

    def test_returns_full_window_when_just_saturated(self) -> None:
        """If the burst just landed, the cool-down is essentially the
        full window."""
        store = RateLimitStore()
        now = time.monotonic()
        store._requests["sliding:2"] = [now] * 10  # noqa: SLF001
        secs = store.seconds_until_next_slot(key="sliding:2", max_requests=10, window_seconds=60)
        assert 59 <= secs <= 61, f"freshly saturated → ~60s, got {secs}"

    def test_returns_minimum_one_when_already_thawed(self) -> None:
        """Even if all entries already aged out (race), Retry-After must
        be a positive integer so iOS doesn't busy-loop."""
        store = RateLimitStore()
        ancient = time.monotonic() - 10_000
        store._requests["sliding:3"] = [ancient] * 5  # noqa: SLF001
        secs = store.seconds_until_next_slot(key="sliding:3", max_requests=10, window_seconds=60)
        assert secs >= 1

    def test_empty_key_falls_back_to_window(self) -> None:
        """Defensive: no entries → return the full window as the hint."""
        store = RateLimitStore()
        secs = store.seconds_until_next_slot(key="never-seen", max_requests=10, window_seconds=60)
        assert secs == 60

    def test_tokens_available_zero_when_saturated(self) -> None:
        """``tokens_available`` is 0 on the 429 path."""
        store = RateLimitStore()
        now = time.monotonic()
        store._requests["sat"] = [now] * 10  # noqa: SLF001
        assert store.tokens_available(key="sat", max_requests=10, window_seconds=60) == 0

    def test_tokens_available_reports_headroom(self) -> None:
        """When 4 of 10 slots used, headroom must be 6."""
        store = RateLimitStore()
        now = time.monotonic()
        store._requests["partial"] = [now] * 4  # noqa: SLF001
        assert store.tokens_available(key="partial", max_requests=10, window_seconds=60) == 6


class TestSlidingRetryAfterIntegration:
    """End-to-end: the middleware MUST surface the sliding hint in both
    the ``Retry-After`` header and the ``rate_limit.retry_after_seconds``
    body field. The header MUST NOT be the fixed 60s value when the
    window is aging."""

    def test_retry_after_reflects_sliding_window(
        self,
        isolated_store: RateLimitStore,
    ) -> None:
        """Backdate the entries, trip the limit, assert the hint shrinks."""
        app = _build_app(isolated_store)
        client = TestClient(app)
        # Saturate with backdated timestamps so the cool-down shrinks.
        backdated = time.monotonic() - 50
        isolated_store._requests["auth:testclient"] = [backdated] * 10  # noqa: SLF001

        resp = client.post("/api/v1/auth/login", json={})
        assert resp.status_code == 429
        retry_after_header = int(resp.headers["Retry-After"])
        body = resp.json()
        retry_after_body = body["rate_limit"]["retry_after_seconds"]

        # Both surfaces must agree.
        assert retry_after_header == retry_after_body
        # And the value MUST be smaller than the full window — the whole
        # point of sliding UX.
        assert retry_after_header < 60
        assert retry_after_header >= 1


# ---------------------------------------------------------------------------
# T2.4 L3 — structured 429 log emit.
# ---------------------------------------------------------------------------


class TestStructured429Log:
    """The 429 path MUST emit a ``rate_limit_exceeded`` log with the
    fields SREs need to triage complaints (endpoint, ip, tokens_consumed,
    tokens_available_after, retry_after_seconds, window_seconds)."""

    def test_log_carries_actionable_fields(
        self,
        isolated_store: RateLimitStore,
    ) -> None:
        app = _build_app(isolated_store)
        client = TestClient(app)

        with structlog.testing.capture_logs() as cap:
            for _ in range(10):
                client.post("/api/v1/auth/login", json={})
            resp = client.post("/api/v1/auth/login", json={})
            assert resp.status_code == 429

        rate_logs = [e for e in cap if e.get("event") == "rate_limit_exceeded"]
        assert rate_logs, "L3: middleware MUST emit a rate_limit_exceeded log"
        entry = rate_logs[-1]
        # Fields the runbook requires for SRE triage:
        assert entry.get("endpoint") == "/api/v1/auth"
        assert "client_ip" in entry
        assert "path" in entry
        assert entry.get("tokens_available_after") == 0
        assert entry.get("tokens_consumed") == 10  # max_requests on 429
        assert entry.get("retry_after_seconds", 0) >= 1
        assert entry.get("window_seconds") == 60
