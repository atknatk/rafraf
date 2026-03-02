"""Unit tests for rate limiting middleware."""

from app.api.middleware.rate_limit import RateLimitStore


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
