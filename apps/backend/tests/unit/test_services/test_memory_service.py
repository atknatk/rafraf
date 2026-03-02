"""Unit tests for MemoryService."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.memory import PersonalMemoryItem
from app.services.memory_service import MemoryService, MemoryServiceError


class TestEstimateTokens:
    """Tests for MemoryService._estimate_tokens."""

    def test_empty_string(self) -> None:
        """Empty string should return 0 tokens."""
        svc = MemoryService()
        assert svc._estimate_tokens("") == 0

    def test_short_string(self) -> None:
        """Short string should return estimated tokens."""
        svc = MemoryService()
        # 8 chars / 4 = 2 tokens
        assert svc._estimate_tokens("12345678") == 2

    def test_long_string(self) -> None:
        """Long string should return proportional tokens."""
        svc = MemoryService()
        text = "a" * 4000
        assert svc._estimate_tokens(text) == 1000


class TestTruncateToBudget:
    """Tests for MemoryService._truncate_to_budget."""

    def test_within_budget(self) -> None:
        """Text within budget should be returned as-is."""
        svc = MemoryService()
        text = "Hello world"
        result = svc._truncate_to_budget(text, 100)
        assert result == text

    def test_exceeds_budget(self) -> None:
        """Text exceeding budget should be truncated with ellipsis."""
        svc = MemoryService()
        text = "a" * 100
        result = svc._truncate_to_budget(text, 10)
        # 10 tokens * 4 chars = 40 chars max
        assert len(result) == 43  # 40 chars + "..."
        assert result.endswith("...")


class TestConversationMemory:
    """Tests for conversation memory (Redis) operations."""

    async def test_save_conversation(self) -> None:
        """save_conversation should delegate to redis_client."""
        svc = MemoryService()
        messages = [{"role": "user", "content": "Hello"}]

        with patch("app.services.memory_service.redis_client") as mock_redis:
            mock_redis.save_conversation = AsyncMock()
            await svc.save_conversation("session_1", messages, ttl=3600)
            mock_redis.save_conversation.assert_called_once_with(
                "session_1", messages, ttl=3600
            )

    async def test_get_conversation(self) -> None:
        """get_conversation should return messages from Redis."""
        svc = MemoryService()
        expected = [{"role": "user", "content": "Test"}]

        with patch("app.services.memory_service.redis_client") as mock_redis:
            mock_redis.get_conversation = AsyncMock(return_value=expected)
            result = await svc.get_conversation("session_1")
            assert result == expected

    async def test_append_message(self) -> None:
        """append_message should delegate to redis_client."""
        svc = MemoryService()
        msg = {"role": "user", "content": "New message"}

        with patch("app.services.memory_service.redis_client") as mock_redis:
            mock_redis.append_message = AsyncMock()
            await svc.append_message("session_1", msg)
            mock_redis.append_message.assert_called_once_with("session_1", msg)

    async def test_clear_conversation(self) -> None:
        """clear_conversation should delete from Redis."""
        svc = MemoryService()

        with patch("app.services.memory_service.redis_client") as mock_redis:
            mock_redis.delete_conversation = AsyncMock(return_value=True)
            result = await svc.clear_conversation("session_1")
            assert result is True


class TestProjectMemory:
    """Tests for project memory (PostgreSQL) operations."""

    async def test_update_project_memory(self) -> None:
        """update_project_memory should call repo.upsert."""
        svc = MemoryService()
        project_id = uuid.uuid4()
        mock_repo = MagicMock()
        mock_row = MagicMock()
        mock_repo.upsert = AsyncMock(return_value=mock_row)

        result = await svc.update_project_memory(
            mock_repo,
            project_id=project_id,
            category="tech_stack",
            key="frontend",
            value={"framework": "React"},
            source="tool_result",
            confidence=0.9,
        )

        mock_repo.upsert.assert_called_once_with(
            project_id=project_id,
            category="tech_stack",
            key="frontend",
            value={"framework": "React"},
            confidence=0.9,
            source="tool_result",
        )
        assert result == mock_row

    async def test_get_project_summary(self) -> None:
        """get_project_summary should return categorized dict."""
        svc = MemoryService()
        project_id = uuid.uuid4()
        mock_repo = MagicMock()
        mock_repo.get_project_summary = AsyncMock(
            return_value={"tech_stack": {"frontend": {"framework": "React"}}}
        )

        result = await svc.get_project_summary(mock_repo, project_id)
        assert "tech_stack" in result
        mock_repo.get_project_summary.assert_called_once_with(project_id)


class TestPersonalMemory:
    """Tests for personal memory (mem0) operations."""

    async def test_search_memories_success(self) -> None:
        """search_memories should return filtered items above threshold."""
        svc = MemoryService()
        mock_mem0 = MagicMock()
        mock_mem0.search.return_value = {
            "results": [
                {"id": "m1", "memory": "User likes short answers", "score": 0.92},
                {"id": "m2", "memory": "Low relevance", "score": 0.50},
                {"id": "m3", "memory": "Medium relevance", "score": 0.75},
            ]
        }
        svc._mem0_client = mock_mem0

        items = await svc.search_memories("user1", "preferences", limit=10)
        assert len(items) == 2  # m2 filtered (score < 0.60)
        assert items[0].id == "m1"
        assert items[1].id == "m3"

    async def test_search_memories_empty_results(self) -> None:
        """search_memories should return empty list for no results."""
        svc = MemoryService()
        mock_mem0 = MagicMock()
        mock_mem0.search.return_value = {"results": []}
        svc._mem0_client = mock_mem0

        items = await svc.search_memories("user1", "unknown topic")
        assert len(items) == 0

    async def test_search_memories_list_format(self) -> None:
        """search_memories should handle list format results."""
        svc = MemoryService()
        mock_mem0 = MagicMock()
        mock_mem0.search.return_value = [
            {"id": "m1", "memory": "Test memory", "score": 0.85},
        ]
        svc._mem0_client = mock_mem0

        items = await svc.search_memories("user1", "query")
        assert len(items) == 1

    async def test_search_memories_error(self) -> None:
        """search_memories should raise MemoryServiceError on failure."""
        svc = MemoryService()
        mock_mem0 = MagicMock()
        mock_mem0.search.side_effect = RuntimeError("Connection lost")
        svc._mem0_client = mock_mem0

        with pytest.raises(MemoryServiceError, match="Hafiza arama basarisiz"):
            await svc.search_memories("user1", "query")

    async def test_save_conversation_facts(self) -> None:
        """save_conversation_facts should call mem0.add and return IDs."""
        svc = MemoryService()
        mock_mem0 = MagicMock()
        mock_mem0.add.return_value = {
            "results": [{"id": "fact_1"}, {"id": "fact_2"}]
        }
        svc._mem0_client = mock_mem0

        messages = [
            {"role": "user", "content": "Use short answers"},
            {"role": "assistant", "content": "OK"},
        ]
        ids = await svc.save_conversation_facts("user1", "sess_1", messages)
        assert len(ids) == 2
        assert "fact_1" in ids

    async def test_save_conversation_facts_error(self) -> None:
        """save_conversation_facts should raise on failure."""
        svc = MemoryService()
        mock_mem0 = MagicMock()
        mock_mem0.add.side_effect = RuntimeError("API error")
        svc._mem0_client = mock_mem0

        with pytest.raises(MemoryServiceError, match="Conversation fact extraction"):
            await svc.save_conversation_facts("user1", "sess_1", [])

    async def test_delete_personal_memory(self) -> None:
        """delete_personal_memory should call mem0.delete."""
        svc = MemoryService()
        mock_mem0 = MagicMock()
        mock_mem0.delete.return_value = None
        svc._mem0_client = mock_mem0

        result = await svc.delete_personal_memory("mem_123")
        assert result is True
        mock_mem0.delete.assert_called_once_with(memory_id="mem_123")

    async def test_delete_personal_memory_error(self) -> None:
        """delete_personal_memory should raise on failure."""
        svc = MemoryService()
        mock_mem0 = MagicMock()
        mock_mem0.delete.side_effect = RuntimeError("Not found")
        svc._mem0_client = mock_mem0

        with pytest.raises(MemoryServiceError, match="Hafiza silme basarisiz"):
            await svc.delete_personal_memory("mem_123")

    async def test_get_all_personal_memories(self) -> None:
        """get_all_personal_memories should return all memories for a user."""
        svc = MemoryService()
        mock_mem0 = MagicMock()
        mock_mem0.get_all.return_value = {
            "results": [
                {"id": "m1", "memory": "Fact 1", "metadata": None},
                {"id": "m2", "memory": "Fact 2", "metadata": {"source": "session"}},
            ]
        }
        svc._mem0_client = mock_mem0

        items = await svc.get_all_personal_memories("user1")
        assert len(items) == 2
        assert items[0].memory == "Fact 1"

    async def test_get_all_personal_memories_error(self) -> None:
        """get_all_personal_memories should raise on failure."""
        svc = MemoryService()
        mock_mem0 = MagicMock()
        mock_mem0.get_all.side_effect = RuntimeError("Error")
        svc._mem0_client = mock_mem0

        with pytest.raises(MemoryServiceError, match="Tum hafizalari getirme basarisiz"):
            await svc.get_all_personal_memories("user1")


class TestGetContextForMessage:
    """Tests for context building."""

    async def test_full_context_build(self) -> None:
        """get_context_for_message should combine all layers."""
        svc = MemoryService()
        project_id = uuid.uuid4()

        # Mock personal memory (mem0)
        mock_mem0 = MagicMock()
        mock_mem0.search.return_value = {
            "results": [
                {"id": "m1", "memory": "User prefers short answers", "score": 0.92},
            ]
        }
        svc._mem0_client = mock_mem0

        # Mock repo
        mock_repo = MagicMock()
        mock_repo.get_project_summary = AsyncMock(
            return_value={"tech_stack": {"frontend": "React"}}
        )

        # Mock redis
        with patch("app.services.memory_service.redis_client") as mock_redis:
            mock_redis.get_cache = AsyncMock(return_value="Previous session about deploy")

            context = await svc.get_context_for_message(
                mock_repo,
                user_id="user1",
                message="What is the project status?",
                project_id=project_id,
                session_id="sess_1",
            )

        assert len(context.personal_memories) == 1
        assert "User prefers short answers" in context.personal_memories
        assert "tech_stack" in context.project_summary
        assert context.conversation_summary is not None
        assert context.token_count > 0

    async def test_context_without_project(self) -> None:
        """get_context_for_message should work without project_id."""
        svc = MemoryService()

        mock_mem0 = MagicMock()
        mock_mem0.search.return_value = {"results": []}
        svc._mem0_client = mock_mem0

        mock_repo = MagicMock()

        with patch("app.services.memory_service.redis_client") as mock_redis:
            mock_redis.get_cache = AsyncMock(return_value=None)

            context = await svc.get_context_for_message(
                mock_repo,
                user_id="user1",
                message="Hello",
            )

        assert context.project_summary == {}
        assert context.conversation_summary is None

    async def test_context_personal_memory_unavailable(self) -> None:
        """get_context_for_message should handle mem0 unavailability."""
        svc = MemoryService()

        # Set mem0_client to something that will fail
        mock_mem0 = MagicMock()
        mock_mem0.search.side_effect = RuntimeError("Connection refused")
        svc._mem0_client = mock_mem0

        mock_repo = MagicMock()
        mock_repo.get_project_summary = AsyncMock(return_value={})

        with patch("app.services.memory_service.redis_client") as mock_redis:
            mock_redis.get_cache = AsyncMock(return_value=None)

            # Should not raise, but return empty personal memories
            context = await svc.get_context_for_message(
                mock_repo,
                user_id="user1",
                message="Test",
                project_id=uuid.uuid4(),
            )

        assert context.personal_memories == []


class TestMem0Initialization:
    """Tests for lazy mem0 initialization."""

    def test_get_mem0_error(self) -> None:
        """_get_mem0 should raise MemoryServiceError if initialization fails."""
        svc = MemoryService()

        with (
            patch("app.services.memory_service.get_settings") as mock_settings,
            pytest.raises(MemoryServiceError, match="mem0 baslatilamadi"),
        ):
            mock_settings.return_value.database_url = "postgresql+asyncpg://test:test@localhost/test"
            mock_settings.return_value.openai_api_key = "sk-test"
            mock_settings.return_value.anthropic_api_key = "sk-ant-test"

            with patch.dict("sys.modules", {"mem0": None}):
                svc._get_mem0()
