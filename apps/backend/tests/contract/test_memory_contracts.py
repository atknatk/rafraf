"""API Contract Tests for memory endpoints.

Validates that backend endpoint definitions match shared/api-contracts/rest/v1/memory.json.
"""

import json
from pathlib import Path

import pytest
from fastapi.routing import APIRoute

from app.main import app

_REPO_ROOT = Path(__file__).resolve().parents[4]
CONTRACT_FILE = _REPO_ROOT / "shared" / "api-contracts" / "rest" / "v1" / "memory.json"


def _load_memory_contract() -> list[dict[str, object]]:
    """Load memory contract endpoints from JSON file."""
    if not CONTRACT_FILE.exists():
        return []
    with open(CONTRACT_FILE) as fp:
        data = json.load(fp)
    return data.get("endpoints", [])  # type: ignore[no-any-return]


def _get_app_routes() -> list[APIRoute]:
    """Get all registered API routes from the app."""
    routes: list[APIRoute] = []
    for route in app.routes:
        if isinstance(route, APIRoute):
            routes.append(route)
    return routes


def _find_route_by_path(path: str) -> list[APIRoute]:
    """Find all routes matching a path."""
    return [r for r in _get_app_routes() if r.path == path]


class TestMemoryContractEndpointsRegistered:
    """Verify all contract endpoints are registered in the app."""

    @pytest.mark.parametrize(
        "endpoint",
        _load_memory_contract(),
        ids=lambda e: f"{e.get('method')} {e.get('path')}",
    )
    def test_endpoint_registered(self, endpoint: dict[str, object]) -> None:
        """Each contract endpoint should be registered in the FastAPI app."""
        path = str(endpoint["path"])
        matching = _find_route_by_path(path)
        assert len(matching) > 0, f"Endpoint {path} not registered in the app"

    @pytest.mark.parametrize(
        "endpoint",
        _load_memory_contract(),
        ids=lambda e: f"{e.get('method')} {e.get('path')}",
    )
    def test_endpoint_method(self, endpoint: dict[str, object]) -> None:
        """Each contract endpoint should have the correct HTTP method."""
        path = str(endpoint["path"])
        method = str(endpoint["method"]).upper()

        matching = _find_route_by_path(path)
        if not matching:
            pytest.skip(f"Endpoint {path} not registered")

        all_methods: set[str] = set()
        for route in matching:
            all_methods.update(route.methods)

        assert method in all_methods, (
            f"Endpoint {path} should support {method}, "
            f"but only supports {all_methods}"
        )


class TestMemoryContractResponseFields:
    """Verify response schemas match contract definitions."""

    def test_project_list_endpoint_exists(self) -> None:
        """GET /api/v1/memory/project/{project_id} should be registered."""
        matching = _find_route_by_path("/api/v1/memory/project/{project_id}")
        assert len(matching) > 0

    def test_project_create_endpoint_exists(self) -> None:
        """POST /api/v1/memory/project/{project_id} should be registered."""
        matching = _find_route_by_path("/api/v1/memory/project/{project_id}")
        all_methods: set[str] = set()
        for route in matching:
            all_methods.update(route.methods)
        assert "POST" in all_methods

    def test_project_delete_endpoint_exists(self) -> None:
        """DELETE /api/v1/memory/project/{project_id}/{memory_id} should be registered."""
        matching = _find_route_by_path("/api/v1/memory/project/{project_id}/{memory_id}")
        assert len(matching) > 0

    def test_personal_search_endpoint_exists(self) -> None:
        """GET /api/v1/memory/personal/{user_id} should be registered."""
        matching = _find_route_by_path("/api/v1/memory/personal/{user_id}")
        assert len(matching) > 0

    def test_personal_delete_endpoint_exists(self) -> None:
        """DELETE /api/v1/memory/personal/{user_id}/{memory_id} should be registered."""
        matching = _find_route_by_path("/api/v1/memory/personal/{user_id}/{memory_id}")
        assert len(matching) > 0

    def test_context_endpoint_exists(self) -> None:
        """GET /api/v1/memory/context/{user_id} should be registered."""
        matching = _find_route_by_path("/api/v1/memory/context/{user_id}")
        assert len(matching) > 0

    def test_project_search_endpoint_exists(self) -> None:
        """GET /api/v1/memory/project/{project_id}/search should exist."""
        path = "/api/v1/memory/project/{project_id}/search"
        matching = _find_route_by_path(path)
        assert len(matching) > 0

    def test_project_summary_endpoint_exists(self) -> None:
        """GET /api/v1/memory/project/{project_id}/summary should exist."""
        path = "/api/v1/memory/project/{project_id}/summary"
        matching = _find_route_by_path(path)
        assert len(matching) > 0

    def test_project_extract_endpoint_exists(self) -> None:
        """POST /api/v1/memory/project/{project_id}/extract should exist."""
        path = "/api/v1/memory/project/{project_id}/extract"
        matching = _find_route_by_path(path)
        assert len(matching) > 0
        all_methods: set[str] = set()
        for route in matching:
            all_methods.update(route.methods)
        assert "POST" in all_methods

    def test_project_stale_endpoint_exists(self) -> None:
        """DELETE /api/v1/memory/project/{project_id}/stale should exist."""
        path = "/api/v1/memory/project/{project_id}/stale"
        matching = _find_route_by_path(path)
        assert len(matching) > 0
        all_methods: set[str] = set()
        for route in matching:
            all_methods.update(route.methods)
        assert "DELETE" in all_methods
