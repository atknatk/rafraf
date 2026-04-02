"""Integration tests for GitHub webhook endpoint."""

import hashlib
import hmac
import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app


def _sign_payload(payload: bytes, secret: str) -> str:
    """Generate GitHub webhook HMAC-SHA256 signature."""
    digest = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


# Mock async_session_factory and WebhookEventService to avoid real DB
_mock_session = AsyncMock()
_mock_evt_svc = MagicMock()
_mock_evt_svc.is_duplicate = AsyncMock(return_value=False)
_mock_evt_svc.record_event = AsyncMock()
_mock_evt_svc.list_events = AsyncMock(return_value=([], 0))


@asynccontextmanager
async def _mock_session_factory():
    yield _mock_session


_session_patch = patch("app.api.routes.webhooks.async_session_factory", _mock_session_factory)
_evt_svc_patch = patch("app.api.routes.webhooks.WebhookEventService", return_value=_mock_evt_svc)
_session_patch.start()
_evt_svc_patch.start()

client = TestClient(app)


class TestGitHubWebhook:
    """Tests for POST /api/v1/webhooks/github."""

    def test_ping_event_accepted(self) -> None:
        """Webhook should accept ping events."""
        payload = {"zen": "Keep it simple", "hook_id": 123}
        body = json.dumps(payload).encode()
        response = client.post(
            "/api/v1/webhooks/github",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-GitHub-Event": "ping",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "accepted"
        assert "ping" in data["message"].lower()

    def test_issue_event_processed(self) -> None:
        """Webhook should process issue events."""
        payload = {
            "action": "opened",
            "issue": {"number": 1, "title": "Test Issue"},
            "repository": {"full_name": "owner/repo"},
            "sender": {"login": "user1"},
        }
        body = json.dumps(payload).encode()
        response = client.post(
            "/api/v1/webhooks/github",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-GitHub-Event": "issues",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "accepted"
        assert "issues" in data["message"].lower()

    def test_pr_event_processed(self) -> None:
        """Webhook should process pull_request events."""
        payload = {
            "action": "closed",
            "pull_request": {"number": 5, "title": "Fix", "merged": True},
            "repository": {"full_name": "owner/repo"},
            "sender": {"login": "user1"},
        }
        body = json.dumps(payload).encode()
        response = client.post(
            "/api/v1/webhooks/github",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-GitHub-Event": "pull_request",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "accepted"
        assert "pull_request" in data["message"].lower()

    def test_push_event_processed(self) -> None:
        """Webhook should process push events."""
        payload = {
            "ref": "refs/heads/main",
            "commits": [{"id": "abc"}],
            "repository": {"full_name": "owner/repo"},
            "sender": {"login": "user1"},
        }
        body = json.dumps(payload).encode()
        response = client.post(
            "/api/v1/webhooks/github",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-GitHub-Event": "push",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "accepted"

    def test_unsupported_event_ignored(self) -> None:
        """Webhook should ignore unsupported event types."""
        payload = {"action": "created", "repository": {"full_name": "owner/repo"}}
        body = json.dumps(payload).encode()
        response = client.post(
            "/api/v1/webhooks/github",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-GitHub-Event": "star",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ignored"

    def test_valid_signature_accepted(self) -> None:
        """Webhook with valid HMAC signature should be accepted."""
        from unittest.mock import patch

        payload = {"action": "opened", "repository": {"full_name": "o/r"}, "sender": {"login": "u"}}
        body = json.dumps(payload).encode()
        signature = _sign_payload(body, "test-secret")

        with patch("app.api.routes.webhooks.get_settings") as mock_settings:
            mock_settings.return_value.github_webhook_secret = "test-secret"
            response = client.post(
                "/api/v1/webhooks/github",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-GitHub-Event": "ping",
                    "X-Hub-Signature-256": signature,
                },
            )
        assert response.status_code == 200

    def test_invalid_signature_rejected(self) -> None:
        """Webhook with invalid HMAC signature should be rejected."""
        from unittest.mock import patch

        payload = {"action": "opened"}
        body = json.dumps(payload).encode()

        with patch("app.api.routes.webhooks.get_settings") as mock_settings:
            mock_settings.return_value.github_webhook_secret = "real-secret"
            response = client.post(
                "/api/v1/webhooks/github",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-GitHub-Event": "ping",
                    "X-Hub-Signature-256": "sha256=invalid",
                },
            )
        assert response.status_code == 401
        data = response.json()
        assert data["status"] == "error"

    def test_missing_signature_rejected_when_secret_configured(self) -> None:
        """Webhook without signature should be rejected when secret is set."""
        from unittest.mock import patch

        payload = {"action": "opened"}
        body = json.dumps(payload).encode()

        with patch("app.api.routes.webhooks.get_settings") as mock_settings:
            mock_settings.return_value.github_webhook_secret = "my-secret"
            response = client.post(
                "/api/v1/webhooks/github",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-GitHub-Event": "ping",
                },
            )
        assert response.status_code == 401
        data = response.json()
        assert data["status"] == "error"
