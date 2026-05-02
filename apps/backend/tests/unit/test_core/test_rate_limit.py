"""Unit tests for rate limiting middleware."""

import json
import time

import pytest
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
