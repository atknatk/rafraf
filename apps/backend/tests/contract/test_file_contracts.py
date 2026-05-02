"""API Contract tests for file sharing endpoints.

Validates that backend file endpoints match the contracts in
shared/api-contracts/rest/v1/files.json.
"""

import json
from pathlib import Path

from app.schemas.files import (
    FileDownloadURLRequest,
    FileDownloadURLResponse,
    FileUploadURLRequest,
    FileUploadURLResponse,
)

_REPO_ROOT = Path(__file__).resolve().parents[4]
REST_CONTRACT = _REPO_ROOT / "shared" / "api-contracts" / "rest" / "v1" / "files.json"


def _load_contract() -> dict[str, object]:
    with open(REST_CONTRACT) as f:
        return json.load(f)  # type: ignore[no-any-return]


class TestRestEndpointRegistration:
    """Verify that REST endpoints declared in the contract exist in the app."""

    def test_upload_url_endpoint_registered(self) -> None:
        """POST /api/v1/files/upload-url should be registered in the FastAPI app."""
        from app.main import app

        routes = {(r.path, ",".join(r.methods or [])) for r in app.routes if hasattr(r, "methods")}
        assert ("/api/v1/files/upload-url", "POST") in routes

    def test_download_url_endpoint_registered(self) -> None:
        """POST /api/v1/files/download-url should be registered in the FastAPI app."""
        from app.main import app

        routes = {(r.path, ",".join(r.methods or [])) for r in app.routes if hasattr(r, "methods")}
        assert ("/api/v1/files/download-url", "POST") in routes


class TestRestContractRequestFields:
    """Verify request schema fields match the contract."""

    def test_upload_request_has_required_fields(self) -> None:
        """FileUploadURLRequest should have all contract-required fields."""
        contract = _load_contract()
        upload_endpoint = next(
            ep
            for ep in contract["endpoints"]  # type: ignore[union-attr]
            if ep["method"] == "POST" and ep["path"] == "/api/v1/files/upload-url"
        )

        required_fields = upload_endpoint["requestBody"]["required"]
        model_fields = set(FileUploadURLRequest.model_fields.keys())

        for field in required_fields:
            assert field in model_fields, f"Missing field: {field}"

    def test_download_request_has_required_fields(self) -> None:
        """FileDownloadURLRequest should have all contract-required fields."""
        contract = _load_contract()
        download_endpoint = next(
            ep
            for ep in contract["endpoints"]  # type: ignore[union-attr]
            if ep["method"] == "POST" and ep["path"] == "/api/v1/files/download-url"
        )

        required_fields = download_endpoint["requestBody"]["required"]
        model_fields = set(FileDownloadURLRequest.model_fields.keys())

        for field in required_fields:
            assert field in model_fields, f"Missing field: {field}"


class TestRestContractResponseFields:
    """Verify response schema fields match the contract."""

    def test_upload_response_has_required_fields(self) -> None:
        """FileUploadURLResponse should have all contract-required fields."""
        contract = _load_contract()
        upload_endpoint = next(
            ep
            for ep in contract["endpoints"]  # type: ignore[union-attr]
            if ep["method"] == "POST" and ep["path"] == "/api/v1/files/upload-url"
        )

        required_fields = upload_endpoint["responseBody"]["required"]
        model_fields = set(FileUploadURLResponse.model_fields.keys())

        for field in required_fields:
            assert field in model_fields, f"Missing field: {field}"

    def test_download_response_has_required_fields(self) -> None:
        """FileDownloadURLResponse should have all contract-required fields."""
        contract = _load_contract()
        download_endpoint = next(
            ep
            for ep in contract["endpoints"]  # type: ignore[union-attr]
            if ep["method"] == "POST" and ep["path"] == "/api/v1/files/download-url"
        )

        required_fields = download_endpoint["responseBody"]["required"]
        model_fields = set(FileDownloadURLResponse.model_fields.keys())

        for field in required_fields:
            assert field in model_fields, f"Missing field: {field}"

    def test_upload_request_fields_match_contract_properties(self) -> None:
        """FileUploadURLRequest fields should match contract requestBody properties."""
        contract = _load_contract()
        upload_endpoint = next(
            ep
            for ep in contract["endpoints"]  # type: ignore[union-attr]
            if ep["method"] == "POST" and ep["path"] == "/api/v1/files/upload-url"
        )

        contract_fields = set(upload_endpoint["requestBody"]["properties"].keys())
        model_fields = set(FileUploadURLRequest.model_fields.keys())

        assert contract_fields == model_fields, (
            f"Contract fields: {contract_fields}, Model fields: {model_fields}"
        )

    def test_download_request_fields_match_contract_properties(self) -> None:
        """FileDownloadURLRequest fields should match contract requestBody properties."""
        contract = _load_contract()
        download_endpoint = next(
            ep
            for ep in contract["endpoints"]  # type: ignore[union-attr]
            if ep["method"] == "POST" and ep["path"] == "/api/v1/files/download-url"
        )

        contract_fields = set(download_endpoint["requestBody"]["properties"].keys())
        model_fields = set(FileDownloadURLRequest.model_fields.keys())

        assert contract_fields == model_fields, (
            f"Contract fields: {contract_fields}, Model fields: {model_fields}"
        )
