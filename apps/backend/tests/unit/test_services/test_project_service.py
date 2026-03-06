"""Unit tests for ProjectService."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import NotFoundError
from app.models.project import Project as ProjectModel
from app.schemas.projects import ProjectStatus
from app.services.project_service import ProjectService


def _make_project_model(
    name: str = "Test Project",
    status: str = "active",
    tech_stack: list[str] | None = None,
) -> ProjectModel:
    """Create a mock Project SQLAlchemy model."""
    project = MagicMock(spec=ProjectModel)
    project.id = uuid.uuid4()
    project.name = name
    project.description = "Test description"
    project.status = status
    project.repository_url = "https://github.com/test/repo"
    project.tech_stack = tech_stack or ["Python"]
    project.last_activity_at = "2026-03-03T10:00:00Z"
    project.last_activity_summary = "PR merged"
    project.local_path = None
    project.source = "manual"
    project.created_at = datetime.now(tz=UTC)
    project.updated_at = datetime.now(tz=UTC)
    return project


class TestGetProjects:
    """Tests for ProjectService.get_projects."""

    async def test_get_projects_returns_list(self) -> None:
        """Should return project list response with correct pagination."""
        mock_session = AsyncMock()
        service = ProjectService(mock_session)

        projects = [_make_project_model("Project 1"), _make_project_model("Project 2")]

        with patch.object(
            service._repo,
            "get_projects",
            new_callable=AsyncMock,
            return_value=(projects, 2),
        ):
            result = await service.get_projects(page=1, page_size=20)

        assert len(result.projects) == 2
        assert result.total == 2
        assert result.page == 1
        assert result.page_size == 20

    async def test_get_projects_with_status_filter(self) -> None:
        """Should pass status filter to repository."""
        mock_session = AsyncMock()
        service = ProjectService(mock_session)

        projects = [_make_project_model("Active", status="active")]

        with patch.object(
            service._repo,
            "get_projects",
            new_callable=AsyncMock,
            return_value=(projects, 1),
        ) as mock_get:
            result = await service.get_projects(
                status_filter=ProjectStatus.ACTIVE,
                page=1,
                page_size=20,
            )

        mock_get.assert_called_once_with(
            status_filter="active",
            agent_id=None,
            page=1,
            page_size=20,
        )
        assert len(result.projects) == 1

    async def test_get_projects_empty_list(self) -> None:
        """Should return empty list when no projects exist."""
        mock_session = AsyncMock()
        service = ProjectService(mock_session)

        with patch.object(
            service._repo,
            "get_projects",
            new_callable=AsyncMock,
            return_value=([], 0),
        ):
            result = await service.get_projects()

        assert result.projects == []
        assert result.total == 0

    async def test_get_projects_maps_status_correctly(self) -> None:
        """Should map ProjectStatus enum to string for summary."""
        mock_session = AsyncMock()
        service = ProjectService(mock_session)

        projects = [_make_project_model("Pending", status="pending")]

        with patch.object(
            service._repo,
            "get_projects",
            new_callable=AsyncMock,
            return_value=(projects, 1),
        ):
            result = await service.get_projects()

        assert result.projects[0].status == ProjectStatus.PENDING


class TestGetProjectById:
    """Tests for ProjectService.get_project_by_id."""

    async def test_get_project_found(self) -> None:
        """Should return project detail when found."""
        mock_session = AsyncMock()
        service = ProjectService(mock_session)
        project = _make_project_model("Found Project")

        with patch.object(
            service._repo,
            "get_by_id",
            new_callable=AsyncMock,
            return_value=project,
        ):
            result = await service.get_project_by_id(project.id)

        assert result.name == "Found Project"
        assert result.id == project.id

    async def test_get_project_not_found_raises(self) -> None:
        """Should raise NotFoundError when project does not exist."""
        mock_session = AsyncMock()
        service = ProjectService(mock_session)
        project_id = uuid.uuid4()

        with patch.object(
            service._repo,
            "get_by_id",
            new_callable=AsyncMock,
            return_value=None,
        ):
            with pytest.raises(NotFoundError):
                await service.get_project_by_id(project_id)

    async def test_get_project_includes_all_fields(self) -> None:
        """Should include all detail fields in response."""
        mock_session = AsyncMock()
        service = ProjectService(mock_session)
        project = _make_project_model("Full Project", tech_stack=["Swift", "Python"])

        with patch.object(
            service._repo,
            "get_by_id",
            new_callable=AsyncMock,
            return_value=project,
        ):
            result = await service.get_project_by_id(project.id)

        assert result.description == "Test description"
        assert result.repository_url == "https://github.com/test/repo"
        assert len(result.tech_stack) == 2
        assert result.last_activity_summary == "PR merged"
