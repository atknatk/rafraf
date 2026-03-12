"""Unit tests for webhook endpoints."""

import hashlib
import hmac
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

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

        # First request
        response1 = client.post(
            "/api/v1/webhooks/github",
            content=payload,
            headers={
                "Content-Type": "application/json",
                "X-GitHub-Event": "ping",
                "X-GitHub-Delivery": delivery_id,
            },
        )
        assert response1.status_code == 200

        # Second request with same delivery ID
        response2 = client.post(
            "/api/v1/webhooks/github",
            content=payload,
            headers={
                "Content-Type": "application/json",
                "X-GitHub-Event": "ping",
                "X-GitHub-Delivery": delivery_id,
            },
        )
        assert response2.status_code == 200
        data2 = response2.json()
        assert data2["status"] == "accepted"
        assert "already processed" in data2["message"].lower()


class TestGitHubWebhookSignature:
    """Tests for HMAC-SHA256 signature verification."""

    @patch("app.api.routes.webhooks.get_settings")
    def test_missing_signature_returns_401(
        self, mock_settings: MagicMock
    ) -> None:
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
    def test_invalid_signature_returns_401(
        self, mock_settings: MagicMock
    ) -> None:
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
    def test_valid_signature_accepted(
        self, mock_settings: MagicMock
    ) -> None:
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
        payload = json.dumps({
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
        }).encode()
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
        payload = json.dumps({
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
        }).encode()
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
        payload = json.dumps({
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
        }).encode()
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
    """Tests for GET /api/v1/webhooks/github/events."""

    def test_list_events_returns_200(self) -> None:
        """GET events endpoint should return 200 with events array."""
        response = client.get("/api/v1/webhooks/github/events")
        assert response.status_code == 200
        data = response.json()
        assert "events" in data
        assert "total" in data
        assert isinstance(data["events"], list)

    def test_list_events_with_type_filter(self) -> None:
        """GET events endpoint with event_type filter should return 200."""
        response = client.get(
            "/api/v1/webhooks/github/events",
            params={"event_type": "check_run"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "events" in data

    def test_list_events_with_limit(self) -> None:
        """GET events endpoint with limit parameter should return 200."""
        response = client.get(
            "/api/v1/webhooks/github/events",
            params={"limit": 5},
        )
        assert response.status_code == 200
