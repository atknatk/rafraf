"""Unit tests for webhook endpoints."""

import hashlib
import hmac
import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app


def _mock_session_factory():
    """Create a mock async_session_factory that returns a mock session."""
    mock_session = AsyncMock()
    mock_event_service_instance = MagicMock()
    mock_event_service_instance.is_duplicate = AsyncMock(return_value=False)
    mock_event_service_instance.record_event = AsyncMock()
    mock_event_service_instance.list_events = AsyncMock(return_value=([], 0))

    @asynccontextmanager
    async def _factory():
        yield mock_session

    return _factory, mock_session, mock_event_service_instance


_factory_fn, _mock_sess, _mock_evt_svc = _mock_session_factory()

# Patch async_session_factory and WebhookEventService globally for this module
_session_patch = patch("app.api.routes.webhooks.async_session_factory", _factory_fn)
_evt_svc_patch = patch("app.api.routes.webhooks.WebhookEventService", return_value=_mock_evt_svc)
_session_patch.start()
_evt_svc_patch.start()

client = TestClient(app)


def _make_signature(payload: bytes, secret: str) -> str:
    """Generate a valid HMAC-SHA256 signature for testing."""
    digest = hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()
    return f"sha256={digest}"


class TestGitHubWebhookIdempotency:
    """Tests for webhook idempotency via X-GitHub-Delivery header."""

    def test_ping_event_accepted(self) -> None:
        """Ping event should be accepted and return status accepted."""
        payload = json.dumps({"zen": "test"}).encode()
        response = client.post(
            "/api/v1/webhooks/github",
            content=payload,
            headers={
                "Content-Type": "application/json",
                "X-GitHub-Event": "ping",
                "X-GitHub-Delivery": "unique-delivery-001",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "accepted"

    def test_duplicate_delivery_returns_already_processed(self) -> None:
        """Second request with same delivery ID should return 'already processed'."""
        payload = json.dumps({"zen": "test"}).encode()
        delivery_id = "dup-test-delivery-002"

        # Make is_duplicate return True to simulate already-processed
        _mock_evt_svc.is_duplicate = AsyncMock(return_value=True)

        response = client.post(
            "/api/v1/webhooks/github",
            content=payload,
            headers={
                "Content-Type": "application/json",
                "X-GitHub-Event": "ping",
                "X-GitHub-Delivery": delivery_id,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "accepted"
        assert "already processed" in data["message"].lower()

        # Reset for other tests
        _mock_evt_svc.is_duplicate = AsyncMock(return_value=False)


class TestGitHubWebhookSignature:
    """Tests for HMAC-SHA256 signature verification."""

    @patch("app.api.routes.webhooks.get_settings")
    def test_missing_signature_returns_401(self, mock_settings: MagicMock) -> None:
        """Request without signature should return 401 when secret is configured."""
        mock_settings.return_value = MagicMock(
            github_webhook_secret="test-secret",
        )
        payload = json.dumps({"action": "opened"}).encode()
        response = client.post(
            "/api/v1/webhooks/github",
            content=payload,
            headers={
                "Content-Type": "application/json",
                "X-GitHub-Event": "issues",
            },
        )
        assert response.status_code == 401

    @patch("app.api.routes.webhooks.get_settings")
    def test_invalid_signature_returns_401(self, mock_settings: MagicMock) -> None:
        """Request with wrong signature should return 401."""
        mock_settings.return_value = MagicMock(
            github_webhook_secret="test-secret",
        )
        payload = json.dumps({"action": "opened"}).encode()
        response = client.post(
            "/api/v1/webhooks/github",
            content=payload,
            headers={
                "Content-Type": "application/json",
                "X-GitHub-Event": "issues",
                "X-Hub-Signature-256": "sha256=invalid",
            },
        )
        assert response.status_code == 401

    @patch("app.api.routes.webhooks.get_settings")
    def test_valid_signature_accepted(self, mock_settings: MagicMock) -> None:
        """Request with valid signature should be accepted."""
        secret = "test-secret"
        mock_settings.return_value = MagicMock(
            github_webhook_secret=secret,
        )
        payload = json.dumps({"zen": "test"}).encode()
        signature = _make_signature(payload, secret)
        response = client.post(
            "/api/v1/webhooks/github",
            content=payload,
            headers={
                "Content-Type": "application/json",
                "X-GitHub-Event": "ping",
                "X-Hub-Signature-256": signature,
                "X-GitHub-Delivery": "sig-test-001",
            },
        )
        assert response.status_code == 200
        assert response.json()["status"] == "accepted"


class TestCheckRunEventHandling:
    """Tests for check_run event processing."""

    def test_check_run_failure_accepted(self) -> None:
        """check_run event with conclusion=failure should be accepted."""
        payload = json.dumps(
            {
                "action": "completed",
                "check_run": {
                    "id": 12345,
                    "name": "CI / tests",
                    "status": "completed",
                    "conclusion": "failure",
                    "html_url": "https://github.com/owner/repo/runs/12345",
                },
                "repository": {"full_name": "owner/repo"},
                "sender": {"login": "github-actions"},
            }
        ).encode()
        response = client.post(
            "/api/v1/webhooks/github",
            content=payload,
            headers={
                "Content-Type": "application/json",
                "X-GitHub-Event": "check_run",
                "X-GitHub-Delivery": "check-run-fail-001",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "accepted"
        assert "check_run" in data["message"]

    def test_check_run_success_accepted(self) -> None:
        """check_run event with conclusion=success should be accepted."""
        payload = json.dumps(
            {
                "action": "completed",
                "check_run": {
                    "id": 12346,
                    "name": "CI / build",
                    "status": "completed",
                    "conclusion": "success",
                    "html_url": "https://github.com/owner/repo/runs/12346",
                },
                "repository": {"full_name": "owner/repo"},
                "sender": {"login": "github-actions"},
            }
        ).encode()
        response = client.post(
            "/api/v1/webhooks/github",
            content=payload,
            headers={
                "Content-Type": "application/json",
                "X-GitHub-Event": "check_run",
                "X-GitHub-Delivery": "check-run-success-001",
            },
        )
        assert response.status_code == 200
        assert response.json()["status"] == "accepted"

    def test_check_run_timed_out_accepted(self) -> None:
        """check_run event with conclusion=timed_out should be accepted."""
        payload = json.dumps(
            {
                "action": "completed",
                "check_run": {
                    "id": 12347,
                    "name": "CI / e2e",
                    "status": "completed",
                    "conclusion": "timed_out",
                    "html_url": "https://github.com/owner/repo/runs/12347",
                },
                "repository": {"full_name": "owner/repo"},
                "sender": {"login": "github-actions"},
            }
        ).encode()
        response = client.post(
            "/api/v1/webhooks/github",
            content=payload,
            headers={
                "Content-Type": "application/json",
                "X-GitHub-Event": "check_run",
                "X-GitHub-Delivery": "check-run-timeout-001",
            },
        )
        assert response.status_code == 200
        assert response.json()["status"] == "accepted"


class TestUnsupportedEventType:
    """Tests for unsupported event types."""

    def test_unsupported_event_returns_ignored(self) -> None:
        """Unknown event type should return status ignored."""
        payload = json.dumps({"action": "test"}).encode()
        response = client.post(
            "/api/v1/webhooks/github",
            content=payload,
            headers={
                "Content-Type": "application/json",
                "X-GitHub-Event": "deployment",
                "X-GitHub-Delivery": "unsupported-001",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ignored"


class TestListGitHubEvents:
    """Tests for GET /api/v1/webhooks/github/events.

    NOTE: This endpoint requires authentication. We override the
    get_current_user dependency to bypass auth in tests.
    """

    def _authed_get(self, path: str, **kwargs: object) -> object:
        """Make an authenticated GET request by overriding auth dependency."""
        from app.api.deps import get_current_user

        mock_user = MagicMock()
        mock_user.id = "test-user-id"
        app.dependency_overrides[get_current_user] = lambda: mock_user
        try:
            return client.get(path, **kwargs)  # type: ignore[arg-type]
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    def test_list_events_returns_200(self) -> None:
        """GET events endpoint should return 200 with events array."""
        response = self._authed_get("/api/v1/webhooks/github/events")
        assert response.status_code == 200  # type: ignore[union-attr]
        data = response.json()  # type: ignore[union-attr]
        assert "events" in data
        assert "total" in data
        assert isinstance(data["events"], list)

    def test_list_events_with_type_filter(self) -> None:
        """GET events endpoint with event_type filter should return 200."""
        response = self._authed_get(
            "/api/v1/webhooks/github/events",
            params={"event_type": "check_run"},
        )
        assert response.status_code == 200  # type: ignore[union-attr]
        data = response.json()  # type: ignore[union-attr]
        assert "events" in data

    def test_list_events_with_limit(self) -> None:
        """GET events endpoint with limit parameter should return 200."""
        response = self._authed_get(
            "/api/v1/webhooks/github/events",
            params={"limit": 5},
        )
        assert response.status_code == 200  # type: ignore[union-attr]
