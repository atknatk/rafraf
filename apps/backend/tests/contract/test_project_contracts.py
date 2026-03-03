"""API Contract tests for project endpoints.

Validates that backend project endpoints match the contracts in
shared/api-contracts/rest/v1/projects.json.
"""

import json
from pathlib import Path

from app.schemas.projects import (
    ProjectDetailResponse,
    ProjectListResponse,
    ProjectSummary,
)

_REPO_ROOT = Path(__file__).resolve().parents[4]
REST_CONTRACT = _REPO_ROOT / "shared" / "api-contracts" / "rest" / "v1" / "projects.json"


def _load_contract() -> dict[str, object]:
    with open(REST_CONTRACT) as f:
        return json.load(f)  # type: ignore[no-any-return]


class TestRestEndpointRegistration:
    """Verify that REST endpoints declared in the contract exist in the app."""

    def test_list_projects_endpoint_registered(self) -> None:
        """GET /api/v1/projects should be registered in the FastAPI app."""
        from app.main import app

        routes = {
            (r.path, ",".join(r.methods or []))
            for r in app.routes
            if hasattr(r, "methods")
        }
        assert ("/api/v1/projects", "GET") in routes

    def test_get_project_endpoint_registered(self) -> None:
        """GET /api/v1/projects/{project_id} should be registered in the FastAPI app."""
        from app.main import app

        paths = [r.path for r in app.routes if hasattr(r, "methods")]
        assert "/api/v1/projects/{project_id}" in paths


class TestRestContractResponseFields:
    """Verify response schema fields match the contract."""

    def test_list_response_has_required_fields(self) -> None:
        """ProjectListResponse should have all contract-required fields."""
        contract = _load_contract()
        list_endpoint = next(
            ep for ep in contract["endpoints"]  # type: ignore[union-attr]
            if ep["method"] == "GET" and ep["path"] == "/api/v1/projects"
        )

        required_fields = list_endpoint["responseBody"]["required"]
        model_fields = set(ProjectListResponse.model_fields.keys())

        for field in required_fields:
            assert field in model_fields, f"Missing field: {field}"

    def test_detail_response_has_required_fields(self) -> None:
        """ProjectDetailResponse should have all contract-required fields."""
        contract = _load_contract()
        detail_endpoint = next(
            ep for ep in contract["endpoints"]  # type: ignore[union-attr]
            if ep["method"] == "GET" and ep["path"] == "/api/v1/projects/{project_id}"
        )

        required_fields = detail_endpoint["responseBody"]["required"]
        model_fields = set(ProjectDetailResponse.model_fields.keys())

        for field in required_fields:
            assert field in model_fields, f"Missing field: {field}"

    def test_summary_fields_match_contract_definition(self) -> None:
        """ProjectSummary should include all fields defined in contract $defs."""
        contract = _load_contract()
        summary_def = contract["$defs"]["ProjectSummary"]  # type: ignore[index]
        contract_fields = set(summary_def["properties"].keys())
        model_fields = set(ProjectSummary.model_fields.keys())

        for field in contract_fields:
            assert field in model_fields, f"Missing summary field: {field}"

    def test_list_response_query_params_match_endpoint(self) -> None:
        """Contract query params should be accepted by the endpoint."""
        contract = _load_contract()
        list_endpoint = next(
            ep for ep in contract["endpoints"]  # type: ignore[union-attr]
            if ep["method"] == "GET" and ep["path"] == "/api/v1/projects"
        )

        query_params = set(list_endpoint["queryParams"]["properties"].keys())
        expected = {"status", "page", "page_size"}
        assert query_params == expected


class TestContractStatusValues:
    """Verify status enum values match the contract."""

    def test_status_enum_values(self) -> None:
        """Project status values should match contract enum."""
        contract = _load_contract()
        detail_endpoint = next(
            ep for ep in contract["endpoints"]  # type: ignore[union-attr]
            if ep["path"] == "/api/v1/projects/{project_id}"
        )
        contract_statuses = set(
            detail_endpoint["responseBody"]["properties"]["status"]["enum"]
        )

        from app.schemas.projects import ProjectStatus

        schema_statuses = {s.value for s in ProjectStatus}
        assert schema_statuses == contract_statuses
