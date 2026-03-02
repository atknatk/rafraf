"""Contract tests for webhook endpoints.

Verifies that the webhook endpoint matches the API contract in
shared/api-contracts/rest/v1/webhooks.json.
"""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

# Navigate from apps/backend/tests/contract/ to repo root (4 levels up)
_REPO_ROOT = Path(__file__).resolve().parents[4]
CONTRACT_PATH = _REPO_ROOT / "shared" / "api-contracts" / "rest" / "v1" / "webhooks.json"

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

    def test_endpoint_path_matches(self) -> None:
        """Endpoint path should match contract."""
        contract = _load_contract()
        endpoints = contract.get("endpoints", [])
        assert isinstance(endpoints, list)
        assert len(endpoints) >= 1

        webhook_ep = endpoints[0]
        assert isinstance(webhook_ep, dict)
        assert webhook_ep["path"] == "/api/v1/webhooks/github"

    def test_endpoint_method_matches(self) -> None:
        """Endpoint HTTP method should match contract."""
        contract = _load_contract()
        endpoints = contract.get("endpoints", [])
        assert isinstance(endpoints, list)
        webhook_ep = endpoints[0]
        assert isinstance(webhook_ep, dict)
        assert webhook_ep["method"] == "POST"

    def test_response_body_has_required_fields(self) -> None:
        """Response should contain required fields from contract."""
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
            },
        )
        data = response.json()
        assert "status" in data
        assert "message" in data

    def test_response_status_values_match_contract(self) -> None:
        """Response status values should be one of the enum values from contract."""
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
            },
        )
        data = response.json()
        assert data["status"] in allowed_values
