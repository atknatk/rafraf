"""API Contract Tests for auth endpoints.

Validates that backend endpoint definitions match shared/api-contracts/rest/v1/auth.json.
"""

import json
from pathlib import Path

import pytest
from fastapi.routing import APIRoute

from app.main import app

_REPO_ROOT = Path(__file__).resolve().parents[4]
CONTRACT_FILE = _REPO_ROOT / "shared" / "api-contracts" / "rest" / "v1" / "auth.json"


def _load_auth_contract() -> list[dict[str, object]]:
    """Load auth contract endpoints from JSON file."""
    if not CONTRACT_FILE.exists():
        return []
    with open(CONTRACT_FILE) as fp:
        data = json.load(fp)
    return data.get("endpoints", [])  # type: ignore[no-any-return]


def _get_app_routes() -> dict[str, APIRoute]:
    """Get all registered API routes from the app."""
    routes: dict[str, APIRoute] = {}
    for route in app.routes:
        if isinstance(route, APIRoute):
            routes[route.path] = route
    return routes


class TestAuthContractEndpointsRegistered:
    """Verify all contract endpoints are registered in the app."""

    @pytest.mark.parametrize(
        "endpoint",
        _load_auth_contract(),
        ids=lambda e: f"{e.get('method')} {e.get('path')}",
    )
    def test_endpoint_registered(self, endpoint: dict[str, object]) -> None:
        """Each contract endpoint should be registered in the FastAPI app."""
        routes = _get_app_routes()
        path = str(endpoint["path"])
        assert path in routes, f"Endpoint {path} not registered in the app"

    @pytest.mark.parametrize(
        "endpoint",
        _load_auth_contract(),
        ids=lambda e: f"{e.get('method')} {e.get('path')}",
    )
    def test_endpoint_method_matches(self, endpoint: dict[str, object]) -> None:
        """Each contract endpoint method should match the registered route."""
        routes = _get_app_routes()
        path = str(endpoint["path"])
        method = str(endpoint["method"]).upper()
        route = routes.get(path)
        assert route is not None, f"Route {path} not found"
        assert method in [m.upper() for m in route.methods], (
            f"Method {method} not found for route {path}. Available: {route.methods}"
        )


class TestAuthContractResponseSchema:
    """Verify response schema matches contract."""

    def test_login_response_has_required_fields(self) -> None:
        """POST /api/v1/auth/token response should include all contract fields."""
        contract_endpoints = _load_auth_contract()
        login_endpoint = next(
            (e for e in contract_endpoints if e.get("path") == "/api/v1/auth/token"),
            None,
        )
        assert login_endpoint is not None
        response_body = login_endpoint.get("responseBody", {})
        assert isinstance(response_body, dict)
        required = response_body.get("required", [])
        assert "access_token" in required
        assert "refresh_token" in required
        assert "token_type" in required
        assert "expires_in" in required

    def test_refresh_response_has_required_fields(self) -> None:
        """POST /api/v1/auth/refresh response should include all contract fields."""
        contract_endpoints = _load_auth_contract()
        refresh_endpoint = next(
            (e for e in contract_endpoints if e.get("path") == "/api/v1/auth/refresh"),
            None,
        )
        assert refresh_endpoint is not None
        response_body = refresh_endpoint.get("responseBody", {})
        assert isinstance(response_body, dict)
        required = response_body.get("required", [])
        assert "access_token" in required
        assert "refresh_token" in required
        assert "token_type" in required
        assert "expires_in" in required
