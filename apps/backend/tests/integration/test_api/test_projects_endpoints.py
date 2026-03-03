"""Integration tests for Project REST endpoints."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.projects import (
    ProjectDetailResponse,
    ProjectListResponse,
    ProjectStatus,
    ProjectSummary,
)


@pytest.fixture
def client() -> TestClient:
    """Create a test client."""
    return TestClient(app)


def _make_list_response(
    count: int = 2,
    status: ProjectStatus = ProjectStatus.ACTIVE,
) -> ProjectListResponse:
    """Create a mock ProjectListResponse."""
    projects = [
        ProjectSummary(
            id=uuid.uuid4(),
            name=f"Project {i}",
            status=status,
            tech_stack=["Python"],
        )
        for i in range(count)
    ]
    return ProjectListResponse(
        projects=projects,
        total=count,
        page=1,
        page_size=20,
    )


def _make_detail_response(
    name: str = "Test Project",
) -> ProjectDetailResponse:
    """Create a mock ProjectDetailResponse."""
    return ProjectDetailResponse(
        id=uuid.uuid4(),
        name=name,
        description="Test description",
        status=ProjectStatus.ACTIVE,
        repository_url="https://github.com/test/repo",
        tech_stack=["Python", "FastAPI"],
        last_activity_at="2026-03-03T10:00:00Z",
        last_activity_summary="PR merged",
        created_at="2026-03-03T10:00:00Z",
        updated_at="2026-03-03T10:00:00Z",
    )


class TestListProjectsEndpoint:
    """Integration tests for GET /api/v1/projects."""

    def test_list_projects_returns_200(self, client: TestClient) -> None:
        """Should return 200 with project list."""
        mock_response = _make_list_response(count=0)

        with patch(
            "app.api.routes.projects.ProjectService",
        ) as mock_cls:
            mock_service = AsyncMock()
            mock_service.get_projects.return_value = mock_response
            mock_cls.return_value = mock_service

            response = client.get("/api/v1/projects")

        assert response.status_code == 200
        data = response.json()
        assert "projects" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data

    def test_list_projects_with_status_filter(self, client: TestClient) -> None:
        """Should accept status query parameter."""
        mock_response = _make_list_response(count=1, status=ProjectStatus.PENDING)

        with patch(
            "app.api.routes.projects.ProjectService",
        ) as mock_cls:
            mock_service = AsyncMock()
            mock_service.get_projects.return_value = mock_response
            mock_cls.return_value = mock_service

            response = client.get("/api/v1/projects?status=pending")

        assert response.status_code == 200

    def test_list_projects_with_pagination(self, client: TestClient) -> None:
        """Should accept page and page_size query parameters."""
        mock_response = _make_list_response(count=1)

        with patch(
            "app.api.routes.projects.ProjectService",
        ) as mock_cls:
            mock_service = AsyncMock()
            mock_service.get_projects.return_value = mock_response
            mock_cls.return_value = mock_service

            response = client.get("/api/v1/projects?page=2&page_size=10")

        assert response.status_code == 200

    def test_list_projects_invalid_status_returns_422(self, client: TestClient) -> None:
        """Should return 422 for invalid status value."""
        response = client.get("/api/v1/projects?status=invalid")
        assert response.status_code == 422

    def test_list_projects_invalid_page_returns_422(self, client: TestClient) -> None:
        """Should return 422 for page < 1."""
        response = client.get("/api/v1/projects?page=0")
        assert response.status_code == 422

    def test_list_projects_invalid_page_size_returns_422(self, client: TestClient) -> None:
        """Should return 422 for page_size > 100."""
        response = client.get("/api/v1/projects?page_size=101")
        assert response.status_code == 422


class TestGetProjectEndpoint:
    """Integration tests for GET /api/v1/projects/{project_id}."""

    def test_get_project_returns_200(self, client: TestClient) -> None:
        """Should return 200 with project details."""
        mock_response = _make_detail_response()

        with patch(
            "app.api.routes.projects.ProjectService",
        ) as mock_cls:
            mock_service = AsyncMock()
            mock_service.get_project_by_id.return_value = mock_response
            mock_cls.return_value = mock_service

            project_id = str(uuid.uuid4())
            response = client.get(f"/api/v1/projects/{project_id}")

        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert "name" in data
        assert "status" in data

    def test_get_project_invalid_uuid_returns_422(self, client: TestClient) -> None:
        """Should return 422 for invalid UUID format."""
        response = client.get("/api/v1/projects/not-a-uuid")
        assert response.status_code == 422
