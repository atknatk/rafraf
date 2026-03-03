"""Unit tests for memory Pydantic schemas."""

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas.memory import (
    ExtractedFact,
    FactExtractionRequest,
    FactExtractionResponse,
    MemoryContext,
    MemoryContextResponse,
    PersonalMemoryItem,
    PersonalMemoryListResponse,
    ProjectMemoryCreateRequest,
    ProjectMemoryEntity,
    ProjectMemoryListResponse,
    ProjectMemoryResponse,
    ProjectSummaryResponse,
    StaleCleanupResponse,
)


class TestProjectMemoryEntity:
    """Tests for ProjectMemoryEntity frozen model."""

    def test_create_valid(self) -> None:
        """Should create a valid entity with all fields."""
        now = datetime.now(tz=UTC)
        entity = ProjectMemoryEntity(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            category="tech_stack",
            key="frontend",
            value={"framework": "Next.js"},
            confidence=0.9,
            source="tool_result",
            last_verified_at=now,
            created_at=now,
            updated_at=now,
        )
        assert entity.category == "tech_stack"
        assert entity.confidence == 0.9

    def test_frozen_cannot_modify(self) -> None:
        """Entity should be immutable (frozen)."""
        now = datetime.now(tz=UTC)
        entity = ProjectMemoryEntity(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            category="tech_stack",
            key="frontend",
            value={"framework": "Next.js"},
            confidence=0.9,
            source="tool_result",
            last_verified_at=None,
            created_at=now,
            updated_at=now,
        )
        with pytest.raises(ValidationError):
            entity.category = "new_category"  # type: ignore[misc]

    def test_optional_last_verified_at(self) -> None:
        """last_verified_at should accept None."""
        now = datetime.now(tz=UTC)
        entity = ProjectMemoryEntity(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            category="known_issues",
            key="bug1",
            value={"description": "Bug"},
            confidence=1.0,
            source="user_stated",
            last_verified_at=None,
            created_at=now,
            updated_at=now,
        )
        assert entity.last_verified_at is None


class TestPersonalMemoryItem:
    """Tests for PersonalMemoryItem frozen model."""

    def test_create_with_score(self) -> None:
        """Should create item with score."""
        item = PersonalMemoryItem(
            id="mem_123",
            memory="User prefers short answers",
            score=0.92,
            metadata={"session_id": "sess_1"},
        )
        assert item.score == 0.92

    def test_create_without_optional_fields(self) -> None:
        """Should create item without score and metadata."""
        item = PersonalMemoryItem(
            id="mem_456",
            memory="User likes detailed logs",
        )
        assert item.score is None
        assert item.metadata is None

    def test_frozen_cannot_modify(self) -> None:
        """Item should be immutable."""
        item = PersonalMemoryItem(id="mem_1", memory="test")
        with pytest.raises(ValidationError):
            item.memory = "changed"  # type: ignore[misc]


class TestMemoryContext:
    """Tests for MemoryContext frozen model."""

    def test_create_full_context(self) -> None:
        """Should create context with all layers."""
        ctx = MemoryContext(
            personal_memories=["mem1", "mem2"],
            project_summary={"tech_stack": {"frontend": "React"}},
            recent_actions=[{"action": "deploy"}],
            conversation_summary="Previous session about CI/CD",
            token_count=1200,
        )
        assert len(ctx.personal_memories) == 2
        assert ctx.token_count == 1200

    def test_defaults(self) -> None:
        """Should have sensible defaults."""
        ctx = MemoryContext(
            personal_memories=[],
            project_summary={},
            recent_actions=[],
        )
        assert ctx.conversation_summary is None
        assert ctx.token_count == 0


class TestProjectMemoryCreateRequest:
    """Tests for ProjectMemoryCreateRequest validation."""

    def test_valid_request(self) -> None:
        """Should accept valid request."""
        req = ProjectMemoryCreateRequest(
            category="tech_stack",
            key="frontend",
            value={"framework": "Next.js"},
        )
        assert req.confidence == 1.0
        assert req.source == "user_stated"

    def test_custom_confidence(self) -> None:
        """Should accept custom confidence."""
        req = ProjectMemoryCreateRequest(
            category="deployment",
            key="last_deploy",
            value={"status": "success"},
            confidence=0.8,
            source="tool_result",
        )
        assert req.confidence == 0.8
        assert req.source == "tool_result"

    def test_confidence_out_of_range_high(self) -> None:
        """Should reject confidence > 1.0."""
        with pytest.raises(ValidationError):
            ProjectMemoryCreateRequest(
                category="test",
                key="test",
                value={},
                confidence=1.5,
            )

    def test_confidence_out_of_range_low(self) -> None:
        """Should reject confidence < 0.0."""
        with pytest.raises(ValidationError):
            ProjectMemoryCreateRequest(
                category="test",
                key="test",
                value={},
                confidence=-0.1,
            )

    def test_category_max_length(self) -> None:
        """Should reject category longer than 50 chars."""
        with pytest.raises(ValidationError):
            ProjectMemoryCreateRequest(
                category="x" * 51,
                key="test",
                value={},
            )

    def test_key_max_length(self) -> None:
        """Should reject key longer than 100 chars."""
        with pytest.raises(ValidationError):
            ProjectMemoryCreateRequest(
                category="test",
                key="x" * 101,
                value={},
            )


class TestProjectMemoryResponse:
    """Tests for ProjectMemoryResponse."""

    def test_create_response(self) -> None:
        """Should create a valid response."""
        now = datetime.now(tz=UTC)
        resp = ProjectMemoryResponse(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            category="tech_stack",
            key="frontend",
            value={"framework": "React"},
            confidence=1.0,
            source="user_stated",
            last_verified_at=None,
            created_at=now,
            updated_at=now,
        )
        assert resp.source == "user_stated"


class TestProjectMemoryListResponse:
    """Tests for ProjectMemoryListResponse."""

    def test_empty_list(self) -> None:
        """Should accept empty items list."""
        resp = ProjectMemoryListResponse(items=[], total=0)
        assert resp.total == 0

    def test_with_items(self) -> None:
        """Should accept list with items."""
        now = datetime.now(tz=UTC)
        item = ProjectMemoryResponse(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            category="test",
            key="test",
            value={},
            confidence=1.0,
            source="user_stated",
            last_verified_at=None,
            created_at=now,
            updated_at=now,
        )
        resp = ProjectMemoryListResponse(items=[item], total=1)
        assert resp.total == 1
        assert len(resp.items) == 1


class TestPersonalMemoryListResponse:
    """Tests for PersonalMemoryListResponse."""

    def test_empty_list(self) -> None:
        """Should accept empty items list."""
        resp = PersonalMemoryListResponse(items=[], total=0)
        assert resp.total == 0


class TestMemoryContextResponse:
    """Tests for MemoryContextResponse."""

    def test_create_response(self) -> None:
        """Should create a valid context response."""
        resp = MemoryContextResponse(
            personal_memories=["memory1"],
            project_summary={"tech_stack": {}},
            conversation_summary=None,
            token_count=500,
        )
        assert resp.token_count == 500
        assert resp.conversation_summary is None


class TestExtractedFact:
    """Tests for ExtractedFact frozen model."""

    def test_create_valid(self) -> None:
        """Should create a valid extracted fact."""
        fact = ExtractedFact(
            category="tech_stack",
            key="frontend",
            value={"framework": "Next.js"},
            confidence=0.9,
        )
        assert fact.category == "tech_stack"
        assert fact.confidence == 0.9

    def test_frozen_cannot_modify(self) -> None:
        """Extracted fact should be immutable."""
        fact = ExtractedFact(
            category="tech_stack",
            key="db",
            value={"type": "postgres"},
            confidence=0.8,
        )
        with pytest.raises(ValidationError):
            fact.category = "deployment"  # type: ignore[misc]


class TestFactExtractionRequest:
    """Tests for FactExtractionRequest validation."""

    def test_valid_request(self) -> None:
        """Should accept valid request with messages."""
        req = FactExtractionRequest(
            messages=[{"role": "user", "content": "test"}],
        )
        assert len(req.messages) == 1
        assert req.source == "ai_inferred"

    def test_empty_messages_rejected(self) -> None:
        """Should reject empty messages list."""
        with pytest.raises(ValidationError):
            FactExtractionRequest(messages=[])

    def test_custom_source(self) -> None:
        """Should accept custom source."""
        req = FactExtractionRequest(
            messages=[{"role": "user", "content": "test"}],
            source="tool_result",
        )
        assert req.source == "tool_result"


class TestFactExtractionResponse:
    """Tests for FactExtractionResponse frozen model."""

    def test_create_response(self) -> None:
        """Should create a valid response."""
        fact = ExtractedFact(
            category="tech_stack",
            key="db",
            value={"type": "postgres"},
            confidence=0.9,
        )
        resp = FactExtractionResponse(
            extracted_facts=[fact],
            total=1,
        )
        assert resp.total == 1
        assert len(resp.extracted_facts) == 1

    def test_empty_response(self) -> None:
        """Should accept empty facts."""
        resp = FactExtractionResponse(
            extracted_facts=[],
            total=0,
        )
        assert resp.total == 0


class TestProjectSummaryResponse:
    """Tests for ProjectSummaryResponse frozen model."""

    def test_create_summary(self) -> None:
        """Should create a valid summary response."""
        now = datetime.now(tz=UTC)
        item = ProjectMemoryResponse(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            category="tech_stack",
            key="frontend",
            value={"framework": "React"},
            confidence=1.0,
            source="user_stated",
            last_verified_at=now,
            created_at=now,
            updated_at=now,
        )
        resp = ProjectSummaryResponse(
            project_id=str(uuid.uuid4()),
            categories={"tech_stack": [item]},
            total_memories=1,
            stale_count=0,
        )
        assert resp.total_memories == 1
        assert resp.stale_count == 0

    def test_empty_summary(self) -> None:
        """Should accept empty summary."""
        resp = ProjectSummaryResponse(
            project_id=str(uuid.uuid4()),
            categories={},
            total_memories=0,
            stale_count=0,
        )
        assert resp.total_memories == 0


class TestStaleCleanupResponse:
    """Tests for StaleCleanupResponse frozen model."""

    def test_create_response(self) -> None:
        """Should create a valid cleanup response."""
        resp = StaleCleanupResponse(
            deleted_count=5,
            threshold_days=30,
        )
        assert resp.deleted_count == 5
        assert resp.threshold_days == 30

    def test_frozen_cannot_modify(self) -> None:
        """Response should be immutable."""
        resp = StaleCleanupResponse(
            deleted_count=0,
            threshold_days=30,
        )
        with pytest.raises(ValidationError):
            resp.deleted_count = 10  # type: ignore[misc]
