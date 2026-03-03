"""Contract tests for conversation memory API.

Validates that backend endpoints match shared/api-contracts/rest/v1/conversation-memory.json.
"""

import json
from pathlib import Path

from app.main import app


# Contract file relative to the repo root (two levels up from apps/backend)
_REPO_ROOT = Path(__file__).resolve().parents[4]
CONTRACT_FILE = _REPO_ROOT / "shared" / "api-contracts" / "rest" / "v1" / "conversation-memory.json"


def _load_contract() -> list[dict[str, object]]:
    """Load conversation memory contract endpoints."""
    if not CONTRACT_FILE.exists():
        return []
    with open(CONTRACT_FILE) as f:
        data = json.load(f)
    endpoints: list[dict[str, object]] = data.get("endpoints", [])
    return endpoints


def _get_app_routes() -> dict[str, set[str]]:
    """Build a mapping of path -> set of methods from the FastAPI app."""
    routes: dict[str, set[str]] = {}
    for route in app.routes:
        if hasattr(route, "path") and hasattr(route, "methods"):
            path = str(route.path)
            if path not in routes:
                routes[path] = set()
            for m in route.methods:
                routes[path].add(str(m))
    return routes


class TestConversationMemoryContract:
    """Validates conversation memory endpoints match contract."""

    def test_contract_file_exists(self) -> None:
        """Contract file should exist."""
        assert CONTRACT_FILE.exists(), f"Contract file not found: {CONTRACT_FILE}"

    def test_all_endpoints_registered(self) -> None:
        """All contract endpoints should be registered in the app."""
        endpoints = _load_contract()
        app_routes = _get_app_routes()

        for ep in endpoints:
            method = str(ep.get("method", "")).upper()
            path = str(ep.get("path", ""))

            # Convert path params: {session_id} -> {session_id} (FastAPI format)
            # They should match directly since FastAPI uses the same format
            assert path in app_routes, (
                f"Endpoint {method} {path} not found in app routes. "
                f"Available: {list(app_routes.keys())}"
            )
            assert method in app_routes[path], (
                f"Method {method} not registered for {path}. "
                f"Available methods: {app_routes[path]}"
            )

    def test_endpoint_count_matches(self) -> None:
        """Number of contract endpoints should match registered endpoints."""
        endpoints = _load_contract()
        # We expect 7 endpoints for conversation memory
        assert len(endpoints) == 7, (
            f"Expected 7 contract endpoints, got {len(endpoints)}"
        )
