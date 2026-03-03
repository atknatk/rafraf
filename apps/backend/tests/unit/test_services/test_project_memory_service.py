"""Unit tests for ProjectMemoryService."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.memory import ExtractedFact
from app.services.project_memory_service import (
    ProjectMemoryService,
    ProjectMemoryServiceError,
    VALID_CATEGORIES,
)


class TestGetConfidenceForSource:
    """Tests for _get_confidence_for_source."""

    def test_user_stated(self) -> None:
        """user_stated should return 1.0."""
        svc = ProjectMemoryService()
        assert svc._get_confidence_for_source("user_stated") == 1.0

    def test_tool_result(self) -> None:
        """tool_result should return 0.9."""
        svc = ProjectMemoryService()
        assert svc._get_confidence_for_source("tool_result") == 0.9

    def test_ai_inferred(self) -> None:
        """ai_inferred should return 0.7."""
        svc = ProjectMemoryService()
        assert svc._get_confidence_for_source("ai_inferred") == 0.7

    def test_unknown_source(self) -> None:
        """Unknown source should fallback to 0.7."""
        svc = ProjectMemoryService()
        assert svc._get_confidence_for_source("unknown") == 0.7


class TestParseExtractionResponse:
    """Tests for _parse_extraction_response."""

    def test_valid_json_response(self) -> None:
        """Should parse valid JSON with facts."""
        svc = ProjectMemoryService()
        response = '{"facts": [{"category": "tech_stack", "key": "db", "value": {"type": "postgres"}, "confidence": 0.9}]}'
        facts = svc._parse_extraction_response(response, "ai_inferred")
        assert len(facts) == 1
        assert facts[0].category == "tech_stack"
        assert facts[0].key == "db"
        assert facts[0].confidence == 0.9

    def test_json_in_code_block(self) -> None:
        """Should extract JSON from markdown code blocks."""
        svc = ProjectMemoryService()
        response = '```json\n{"facts": [{"category": "status", "key": "sprint", "value": {"current": "Sprint 5"}, "confidence": 0.8}]}\n```'
        facts = svc._parse_extraction_response(response, "ai_inferred")
        assert len(facts) == 1
        assert facts[0].category == "status"

    def test_json_in_plain_code_block(self) -> None:
        """Should extract JSON from plain code blocks."""
        svc = ProjectMemoryService()
        response = '```\n{"facts": [{"category": "deployment", "key": "env", "value": {"type": "production"}, "confidence": 0.85}]}\n```'
        facts = svc._parse_extraction_response(response, "ai_inferred")
        assert len(facts) == 1

    def test_empty_facts(self) -> None:
        """Should return empty list for no facts."""
        svc = ProjectMemoryService()
        response = '{"facts": []}'
        facts = svc._parse_extraction_response(response, "ai_inferred")
        assert len(facts) == 0

    def test_invalid_json(self) -> None:
        """Should return empty list for invalid JSON."""
        svc = ProjectMemoryService()
        response = "This is not JSON"
        facts = svc._parse_extraction_response(response, "ai_inferred")
        assert len(facts) == 0

    def test_invalid_category_filtered(self) -> None:
        """Should filter out facts with invalid categories."""
        svc = ProjectMemoryService()
        response = '{"facts": [{"category": "invalid_cat", "key": "test", "value": {"x": 1}, "confidence": 0.8}]}'
        facts = svc._parse_extraction_response(response, "ai_inferred")
        assert len(facts) == 0

    def test_missing_required_fields(self) -> None:
        """Should skip facts with missing required fields."""
        svc = ProjectMemoryService()
        response = '{"facts": [{"category": "tech_stack"}, {"key": "test"}, {"category": "tech_stack", "key": "db", "value": {"x": 1}, "confidence": 0.9}]}'
        facts = svc._parse_extraction_response(response, "ai_inferred")
        assert len(facts) == 1

    def test_non_dict_value_wrapped(self) -> None:
        """Should wrap non-dict values in a dict."""
        svc = ProjectMemoryService()
        response = '{"facts": [{"category": "tech_stack", "key": "lang", "value": "Python", "confidence": 0.9}]}'
        facts = svc._parse_extraction_response(response, "ai_inferred")
        assert len(facts) == 1
        assert facts[0].value == {"value": "Python"}

    def test_confidence_clamped(self) -> None:
        """Should clamp confidence to [0.0, 1.0]."""
        svc = ProjectMemoryService()
        response = '{"facts": [{"category": "tech_stack", "key": "db", "value": {"x": 1}, "confidence": 1.5}]}'
        facts = svc._parse_extraction_response(response, "ai_inferred")
        assert facts[0].confidence == 1.0

    def test_key_truncated(self) -> None:
        """Should truncate key to 100 chars."""
        svc = ProjectMemoryService()
        long_key = "x" * 150
        response = f'{{"facts": [{{"category": "tech_stack", "key": "{long_key}", "value": {{"x": 1}}, "confidence": 0.8}}]}}'
        facts = svc._parse_extraction_response(response, "ai_inferred")
        assert len(facts[0].key) == 100

    def test_default_confidence_used(self) -> None:
        """Should use default confidence when not a number."""
        svc = ProjectMemoryService()
        response = '{"facts": [{"category": "tech_stack", "key": "db", "value": {"x": 1}, "confidence": "high"}]}'
        facts = svc._parse_extraction_response(response, "ai_inferred")
        assert facts[0].confidence == 0.7  # ai_inferred default

    def test_all_valid_categories(self) -> None:
        """Should accept all valid categories."""
        svc = ProjectMemoryService()
        for cat in VALID_CATEGORIES:
            response = f'{{"facts": [{{"category": "{cat}", "key": "test", "value": {{"x": 1}}, "confidence": 0.8}}]}}'
            facts = svc._parse_extraction_response(response, "ai_inferred")
            assert len(facts) == 1, f"Category {cat} should be valid"

    def test_non_list_facts_field(self) -> None:
        """Should return empty for non-list facts field."""
        svc = ProjectMemoryService()
        response = '{"facts": "not a list"}'
        facts = svc._parse_extraction_response(response, "ai_inferred")
        assert len(facts) == 0

    def test_non_dict_items_in_facts(self) -> None:
        """Should skip non-dict items in facts array."""
        svc = ProjectMemoryService()
        response = '{"facts": ["string_item", 42, {"category": "tech_stack", "key": "db", "value": {"x": 1}, "confidence": 0.8}]}'
        facts = svc._parse_extraction_response(response, "ai_inferred")
        assert len(facts) == 1


class TestSearchProjectMemories:
    """Tests for search_project_memories."""

    async def test_search_returns_responses(self) -> None:
        """Should return ProjectMemoryResponse list from repo."""
        svc = ProjectMemoryService()
        project_id = uuid.uuid4()
        now = datetime.now(tz=UTC)

        mock_row = MagicMock()
        mock_row.id = uuid.uuid4()
        mock_row.project_id = project_id
        mock_row.category = "tech_stack"
        mock_row.key = "frontend"
        mock_row.value = {"framework": "React"}
        mock_row.confidence = 0.9
        mock_row.source = "ai_inferred"
        mock_row.last_verified_at = now
        mock_row.created_at = now
        mock_row.updated_at = now

        mock_repo = MagicMock()
        mock_repo.search = AsyncMock(return_value=[mock_row])

        results = await svc.search_project_memories(
            mock_repo, project_id, query="React"
        )
        assert len(results) == 1
        assert results[0].category == "tech_stack"
        mock_repo.search.assert_called_once_with(
            project_id=project_id,
            query="React",
            category=None,
            min_confidence=0.0,
        )

    async def test_search_empty_results(self) -> None:
        """Should return empty list when no matches."""
        svc = ProjectMemoryService()
        mock_repo = MagicMock()
        mock_repo.search = AsyncMock(return_value=[])

        results = await svc.search_project_memories(
            mock_repo, uuid.uuid4(), query="nonexistent"
        )
        assert len(results) == 0


class TestGetProjectSummary:
    """Tests for get_project_summary."""

    async def test_summary_with_data(self) -> None:
        """Should return summary with categories and counts."""
        svc = ProjectMemoryService()
        project_id = uuid.uuid4()
        now = datetime.now(tz=UTC)

        mock_row = MagicMock()
        mock_row.id = uuid.uuid4()
        mock_row.project_id = project_id
        mock_row.category = "tech_stack"
        mock_row.key = "frontend"
        mock_row.value = {"framework": "React"}
        mock_row.confidence = 0.9
        mock_row.source = "ai_inferred"
        mock_row.last_verified_at = now
        mock_row.created_at = now
        mock_row.updated_at = now

        mock_repo = MagicMock()
        mock_repo.get_all_grouped_by_category = AsyncMock(
            return_value={"tech_stack": [mock_row]}
        )
        mock_repo.count_stale_entries = AsyncMock(return_value=2)

        summary = await svc.get_project_summary(mock_repo, project_id)
        assert summary.total_memories == 1
        assert summary.stale_count == 2
        assert "tech_stack" in summary.categories
        assert summary.project_id == str(project_id)

    async def test_summary_empty_project(self) -> None:
        """Should return empty summary for project with no memories."""
        svc = ProjectMemoryService()
        mock_repo = MagicMock()
        mock_repo.get_all_grouped_by_category = AsyncMock(return_value={})
        mock_repo.count_stale_entries = AsyncMock(return_value=0)

        summary = await svc.get_project_summary(mock_repo, uuid.uuid4())
        assert summary.total_memories == 0
        assert summary.stale_count == 0
        assert summary.categories == {}


class TestExtractFactsFromMessages:
    """Tests for extract_facts_from_messages."""

    async def test_extract_success(self) -> None:
        """Should call Claude API and return extracted facts."""
        svc = ProjectMemoryService()
        messages = [
            {"role": "user", "content": "Projede Next.js 15 kullaniyoruz"},
            {"role": "assistant", "content": "Anladim"},
        ]

        mock_block = MagicMock()
        mock_block.text = (
            '{"facts": [{"category": "tech_stack", "key": "frontend",'
            ' "value": {"framework": "Next.js", "version": "15"},'
            ' "confidence": 0.9}]}'
        )
        mock_response = MagicMock()
        mock_response.content = [mock_block]

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        mock_anthropic = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client

        with patch.dict(
            "sys.modules", {"anthropic": mock_anthropic}
        ):
            result = await svc.extract_facts_from_messages(messages)
            assert result.total == 1
            assert result.extracted_facts[0].category == "tech_stack"

    async def test_extract_api_error(self) -> None:
        """Should raise ProjectMemoryServiceError on API failure."""
        svc = ProjectMemoryService()

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = RuntimeError("API err")

        mock_anthropic = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client

        with (
            patch.dict("sys.modules", {"anthropic": mock_anthropic}),
            pytest.raises(
                ProjectMemoryServiceError,
                match="Fact extraction basarisiz",
            ),
        ):
            await svc.extract_facts_from_messages(
                [{"role": "user", "content": "test"}]
            )


class TestExtractAndSaveFacts:
    """Tests for extract_and_save_facts."""

    async def test_extract_and_save(self) -> None:
        """Should extract facts and upsert them to repo."""
        svc = ProjectMemoryService()
        project_id = uuid.uuid4()

        mock_block = MagicMock()
        mock_block.text = (
            '{"facts": [{"category": "tech_stack", "key": "db",'
            ' "value": {"type": "postgres"}, "confidence": 0.9}]}'
        )
        mock_response = MagicMock()
        mock_response.content = [mock_block]

        mock_repo = MagicMock()
        mock_repo.upsert = AsyncMock(return_value=MagicMock())

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        mock_anthropic = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client

        with patch.dict(
            "sys.modules", {"anthropic": mock_anthropic}
        ):
            result = await svc.extract_and_save_facts(
                mock_repo,
                project_id,
                [{"role": "user", "content": "We use postgres"}],
            )

        assert result.total == 1
        mock_repo.upsert.assert_called_once()
        call_kwargs = mock_repo.upsert.call_args.kwargs
        assert call_kwargs["project_id"] == project_id
        assert call_kwargs["category"] == "tech_stack"
        assert call_kwargs["key"] == "db"


class TestCleanupStaleEntries:
    """Tests for cleanup_stale_entries."""

    async def test_cleanup_returns_count(self) -> None:
        """Should delete stale entries and return count."""
        svc = ProjectMemoryService()
        project_id = uuid.uuid4()

        mock_repo = MagicMock()
        mock_repo.delete_stale_entries = AsyncMock(return_value=5)

        result = await svc.cleanup_stale_entries(mock_repo, project_id, 30)
        assert result.deleted_count == 5
        assert result.threshold_days == 30
        mock_repo.delete_stale_entries.assert_called_once_with(
            project_id, 30
        )

    async def test_cleanup_no_stale(self) -> None:
        """Should return 0 when no stale entries."""
        svc = ProjectMemoryService()
        mock_repo = MagicMock()
        mock_repo.delete_stale_entries = AsyncMock(return_value=0)

        result = await svc.cleanup_stale_entries(
            mock_repo, uuid.uuid4(), 60
        )
        assert result.deleted_count == 0
        assert result.threshold_days == 60
