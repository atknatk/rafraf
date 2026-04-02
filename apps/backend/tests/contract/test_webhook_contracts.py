"""Contract tests for webhook endpoints.

Verifies that the webhook endpoint matches the API contract in
shared/api-contracts/rest/v1/webhooks.json.
"""

import json
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app

# Navigate from apps/backend/tests/contract/ to repo root (4 levels up)
_REPO_ROOT = Path(__file__).resolve().parents[4]
CONTRACT_PATH = _REPO_ROOT / "shared" / "api-contracts" / "rest" / "v1" / "webhooks.json"

# Mock async_session_factory and WebhookEventService to avoid real DB connections
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


def _load_contract() -> dict[str, object]:
    """Load the webhook contract file."""
    with open(CONTRACT_PATH) as f:
        return json.load(f)  # type: ignore[no-any-return]


class TestWebhookContractCompliance:
    """Tests that webhook endpoint matches shared/api-contracts/rest/v1/webhooks.json."""

    def test_contract_file_exists(self) -> None:
        """Contract file should exist."""
        assert CONTRACT_PATH.exists(), f"Contract file not found: {CONTRACT_PATH}"

    def test_post_endpoint_path_matches(self) -> None:
        """POST endpoint path should match contract."""
        contract = _load_contract()
        endpoints = contract.get("endpoints", [])
        assert isinstance(endpoints, list)
        assert len(endpoints) >= 1

        webhook_ep = endpoints[0]
        assert isinstance(webhook_ep, dict)
        assert webhook_ep["path"] == "/api/v1/webhooks/github"

    def test_post_endpoint_method_matches(self) -> None:
        """POST endpoint HTTP method should match contract."""
        contract = _load_contract()
        endpoints = contract.get("endpoints", [])
        assert isinstance(endpoints, list)
        webhook_ep = endpoints[0]
        assert isinstance(webhook_ep, dict)
        assert webhook_ep["method"] == "POST"

    def test_get_events_endpoint_exists_in_contract(self) -> None:
        """GET events endpoint should be defined in contract."""
        contract = _load_contract()
        endpoints = contract.get("endpoints", [])
        assert isinstance(endpoints, list)
        assert len(endpoints) >= 2

        events_ep = endpoints[1]
        assert isinstance(events_ep, dict)
        assert events_ep["path"] == "/api/v1/webhooks/github/events"
        assert events_ep["method"] == "GET"

    def test_get_events_query_params_match_contract(self) -> None:
        """GET events query params should match contract."""
        contract = _load_contract()
        endpoints = contract.get("endpoints", [])
        assert isinstance(endpoints, list)
        events_ep = endpoints[1]
        assert isinstance(events_ep, dict)
        query_params = events_ep.get("queryParams", {})
        assert isinstance(query_params, dict)
        props = query_params.get("properties", {})
        assert isinstance(props, dict)
        assert "limit" in props
        assert "event_type" in props

    def test_post_response_body_has_required_fields(self) -> None:
        """POST response should contain required fields from contract."""
        contract = _load_contract()
        endpoints = contract.get("endpoints", [])
        assert isinstance(endpoints, list)
        webhook_ep = endpoints[0]
        assert isinstance(webhook_ep, dict)
        response_schema = webhook_ep.get("responseBody", {})
        assert isinstance(response_schema, dict)
        required = response_schema.get("required", [])
        assert "status" in required
        assert "message" in required

        # Verify actual endpoint returns these fields
        payload = json.dumps({"action": "test"}).encode()
        response = client.post(
            "/api/v1/webhooks/github",
            content=payload,
            headers={
                "Content-Type": "application/json",
                "X-GitHub-Event": "ping",
                "X-GitHub-Delivery": "contract-test-001",
            },
        )
        data = response.json()
        assert "status" in data
        assert "message" in data

    def test_post_response_status_values_match_contract(self) -> None:
        """POST response status values should be one of the enum values from contract."""
        contract = _load_contract()
        endpoints = contract.get("endpoints", [])
        assert isinstance(endpoints, list)
        webhook_ep = endpoints[0]
        assert isinstance(webhook_ep, dict)
        response_schema = webhook_ep.get("responseBody", {})
        assert isinstance(response_schema, dict)
        properties = response_schema.get("properties", {})
        assert isinstance(properties, dict)
        status_prop = properties.get("status", {})
        assert isinstance(status_prop, dict)
        allowed_values = status_prop.get("enum", [])

        # Test ping returns valid status
        payload = json.dumps({"zen": "test"}).encode()
        response = client.post(
            "/api/v1/webhooks/github",
            content=payload,
            headers={
                "Content-Type": "application/json",
                "X-GitHub-Event": "ping",
                "X-GitHub-Delivery": "contract-test-002",
            },
        )
        data = response.json()
        assert data["status"] in allowed_values

    def test_get_events_response_has_required_fields(self) -> None:
        """GET events response should contain required fields from contract."""
        contract = _load_contract()
        endpoints = contract.get("endpoints", [])
        assert isinstance(endpoints, list)
        events_ep = endpoints[1]
        assert isinstance(events_ep, dict)
        response_schema = events_ep.get("responseBody", {})
        assert isinstance(response_schema, dict)
        required = response_schema.get("required", [])
        assert "events" in required
        assert "total" in required

        # Verify actual endpoint returns these fields (override auth)
        from app.api.deps import get_current_user
        mock_user = MagicMock()
        mock_user.id = "test-user-id"
        app.dependency_overrides[get_current_user] = lambda: mock_user
        try:
            response = client.get("/api/v1/webhooks/github/events")
            data = response.json()
            assert "events" in data
            assert "total" in data
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    def test_check_run_event_supported_in_contract(self) -> None:
        """Contract should document check_run in requestBody properties."""
        contract = _load_contract()
        endpoints = contract.get("endpoints", [])
        assert isinstance(endpoints, list)
        webhook_ep = endpoints[0]
        assert isinstance(webhook_ep, dict)
        request_body = webhook_ep.get("requestBody", {})
        assert isinstance(request_body, dict)
        properties = request_body.get("properties", {})
        assert isinstance(properties, dict)
        assert "check_run" in properties
