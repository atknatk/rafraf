"""Contract tests for proactive notification API endpoints.

Validates that backend endpoint definitions match the shared API contracts
in shared/api-contracts/rest/v1/proactive-notifications.json.
"""

import json
from pathlib import Path

import pytest

CONTRACT_FILE = (
    Path(__file__).resolve().parents[4]
    / "shared/api-contracts/rest/v1/proactive-notifications.json"
)


@pytest.fixture
def contract_endpoints() -> list[dict[str, object]]:
    """Load proactive notification contract endpoints."""
    if not CONTRACT_FILE.exists():
        pytest.skip("Contract file not found")
    with open(CONTRACT_FILE) as f:
        data = json.load(f)
    return data.get("endpoints", [])


class TestProactiveNotificationContracts:
    """Validates backend routes match API contract definitions."""

    def test_contract_file_exists(self) -> None:
        """Contract file should exist."""
        assert CONTRACT_FILE.exists(), f"Contract file not found: {CONTRACT_FILE}"

    def test_contract_has_endpoints(
        self,
        contract_endpoints: list[dict[str, object]],
    ) -> None:
        """Contract should define at least 5 endpoints."""
        assert len(contract_endpoints) >= 5

    def test_list_endpoint_defined(
        self,
        contract_endpoints: list[dict[str, object]],
    ) -> None:
        """GET /api/v1/proactive-notifications should be defined."""
        endpoint = next(
            (
                e
                for e in contract_endpoints
                if e.get("method") == "GET" and e.get("path") == "/api/v1/proactive-notifications"
            ),
            None,
        )
        assert endpoint is not None, "GET /api/v1/proactive-notifications not found"
        response = endpoint.get("responseBody", {})
        assert isinstance(response, dict)
        props = response.get("properties", {})
        assert "notifications" in props
        assert "total" in props
        assert "page" in props
        assert "page_size" in props

    def test_mark_read_endpoint_defined(
        self,
        contract_endpoints: list[dict[str, object]],
    ) -> None:
        """PATCH /api/v1/proactive-notifications/{notification_id}/read should be defined."""
        endpoint = next(
            (
                e
                for e in contract_endpoints
                if e.get("method") == "PATCH" and "read" in str(e.get("path", ""))
            ),
            None,
        )
        assert endpoint is not None, "PATCH read endpoint not found"

    def test_read_all_endpoint_defined(
        self,
        contract_endpoints: list[dict[str, object]],
    ) -> None:
        """POST /api/v1/proactive-notifications/read-all should be defined."""
        endpoint = next(
            (
                e
                for e in contract_endpoints
                if e.get("method") == "POST" and "read-all" in str(e.get("path", ""))
            ),
            None,
        )
        assert endpoint is not None, "POST read-all endpoint not found"
        response = endpoint.get("responseBody", {})
        assert isinstance(response, dict)
        assert "marked_count" in response.get("properties", {})

    def test_delete_endpoint_defined(
        self,
        contract_endpoints: list[dict[str, object]],
    ) -> None:
        """DELETE /api/v1/proactive-notifications/{notification_id} should be defined."""
        endpoint = next(
            (e for e in contract_endpoints if e.get("method") == "DELETE"),
            None,
        )
        assert endpoint is not None, "DELETE endpoint not found"

    def test_unread_count_endpoint_defined(
        self,
        contract_endpoints: list[dict[str, object]],
    ) -> None:
        """GET /api/v1/proactive-notifications/unread-count should be defined."""
        endpoint = next(
            (
                e
                for e in contract_endpoints
                if e.get("method") == "GET" and "unread-count" in str(e.get("path", ""))
            ),
            None,
        )
        assert endpoint is not None, "GET unread-count endpoint not found"
        response = endpoint.get("responseBody", {})
        assert isinstance(response, dict)
        assert "count" in response.get("properties", {})

    def test_list_query_params(
        self,
        contract_endpoints: list[dict[str, object]],
    ) -> None:
        """List endpoint should define expected query parameters."""
        endpoint = next(
            (
                e
                for e in contract_endpoints
                if e.get("method") == "GET" and e.get("path") == "/api/v1/proactive-notifications"
            ),
            None,
        )
        assert endpoint is not None
        query_params = endpoint.get("queryParams", {})
        assert isinstance(query_params, dict)
        props = query_params.get("properties", {})
        assert "page" in props
        assert "page_size" in props
        assert "priority" in props
        assert "is_read" in props
        assert "type" in props

    def test_notification_response_fields(self) -> None:
        """Notification response should have required fields per contract."""
        # Load the $defs section
        with open(CONTRACT_FILE) as f:
            data = json.load(f)
        defs = data.get("$defs", {})
        notification_schema = defs.get("ProactiveNotificationResponse", {})
        assert notification_schema, "ProactiveNotificationResponse $def not found"

        props = notification_schema.get("properties", {})
        required = notification_schema.get("required", [])

        # Check all required fields exist
        assert "id" in props
        assert "type" in props
        assert "priority" in props
        assert "title" in props
        assert "body" in props
        assert "source" in props
        assert "is_read" in props
        assert "created_at" in props

        assert "id" in required
        assert "type" in required
        assert "priority" in required
        assert "title" in required
        assert "body" in required
        assert "source" in required
        assert "is_read" in required
        assert "created_at" in required
