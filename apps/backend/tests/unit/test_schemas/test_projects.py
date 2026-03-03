"""Unit tests for project Pydantic schemas."""

import uuid

import pytest
from pydantic import ValidationError

from app.schemas.projects import (
    ProjectDetailResponse,
    ProjectEntity,
    ProjectListResponse,
    ProjectStatus,
    ProjectSummary,
)


class TestProjectStatus:
    """Tests for ProjectStatus enum."""

    def test_active_value(self) -> None:
        assert ProjectStatus.ACTIVE == "active"

    def test_pending_value(self) -> None:
        assert ProjectStatus.PENDING == "pending"

    def test_completed_value(self) -> None:
        assert ProjectStatus.COMPLETED == "completed"


class TestProjectEntity:
    """Tests for ProjectEntity frozen model."""

    def test_create_valid_entity(self) -> None:
        entity = ProjectEntity(
            id=uuid.uuid4(),
            name="Test Project",
            status=ProjectStatus.ACTIVE,
            created_at="2026-03-03T10:00:00Z",
            updated_at="2026-03-03T10:00:00Z",
        )
        assert entity.name == "Test Project"
        assert entity.status == ProjectStatus.ACTIVE
        assert entity.description is None
        assert entity.tech_stack == []

    def test_entity_is_frozen(self) -> None:
        entity = ProjectEntity(
            id=uuid.uuid4(),
            name="Test",
            status=ProjectStatus.ACTIVE,
            created_at="2026-03-03T10:00:00Z",
            updated_at="2026-03-03T10:00:00Z",
        )
        with pytest.raises(ValidationError):
            entity.name = "Changed"  # type: ignore[misc]

    def test_entity_with_optional_fields(self) -> None:
        entity = ProjectEntity(
            id=uuid.uuid4(),
            name="Full Project",
            description="A detailed project",
            status=ProjectStatus.PENDING,
            repository_url="https://github.com/test/repo",
            tech_stack=["Python", "FastAPI"],
            last_activity_at="2026-03-03T10:00:00Z",
            last_activity_summary="PR merged",
            created_at="2026-03-03T10:00:00Z",
            updated_at="2026-03-03T10:00:00Z",
        )
        assert entity.description == "A detailed project"
        assert entity.repository_url == "https://github.com/test/repo"
        assert len(entity.tech_stack) == 2

    def test_entity_requires_name(self) -> None:
        with pytest.raises(ValidationError):
            ProjectEntity(
                id=uuid.uuid4(),
                status=ProjectStatus.ACTIVE,
                created_at="2026-03-03T10:00:00Z",
                updated_at="2026-03-03T10:00:00Z",
            )  # type: ignore[call-arg]


class TestProjectSummary:
    """Tests for ProjectSummary DTO."""

    def test_create_summary(self) -> None:
        summary = ProjectSummary(
            id=uuid.uuid4(),
            name="Project",
            status=ProjectStatus.ACTIVE,
            tech_stack=["Swift"],
        )
        assert summary.name == "Project"
        assert summary.last_activity_at is None

    def test_summary_with_activity(self) -> None:
        summary = ProjectSummary(
            id=uuid.uuid4(),
            name="Project",
            status=ProjectStatus.ACTIVE,
            last_activity_at="2026-03-03T10:00:00Z",
            last_activity_summary="Build succeeded",
            tech_stack=["Python"],
        )
        assert summary.last_activity_summary == "Build succeeded"


class TestProjectListResponse:
    """Tests for ProjectListResponse DTO."""

    def test_create_list_response(self) -> None:
        response = ProjectListResponse(
            projects=[],
            total=0,
            page=1,
            page_size=20,
        )
        assert response.total == 0
        assert response.projects == []

    def test_list_response_with_projects(self) -> None:
        project = ProjectSummary(
            id=uuid.uuid4(),
            name="Test",
            status=ProjectStatus.ACTIVE,
            tech_stack=[],
        )
        response = ProjectListResponse(
            projects=[project],
            total=1,
            page=1,
            page_size=20,
        )
        assert len(response.projects) == 1
        assert response.total == 1

    def test_list_response_rejects_negative_total(self) -> None:
        with pytest.raises(ValidationError):
            ProjectListResponse(
                projects=[],
                total=-1,
                page=1,
                page_size=20,
            )

    def test_list_response_rejects_zero_page(self) -> None:
        with pytest.raises(ValidationError):
            ProjectListResponse(
                projects=[],
                total=0,
                page=0,
                page_size=20,
            )


class TestProjectDetailResponse:
    """Tests for ProjectDetailResponse DTO."""

    def test_create_detail_response(self) -> None:
        detail = ProjectDetailResponse(
            id=uuid.uuid4(),
            name="Detail Project",
            status=ProjectStatus.COMPLETED,
            tech_stack=["Node.js"],
            created_at="2026-03-03T10:00:00Z",
            updated_at="2026-03-03T10:00:00Z",
        )
        assert detail.name == "Detail Project"
        assert detail.status == ProjectStatus.COMPLETED
        assert detail.description is None
