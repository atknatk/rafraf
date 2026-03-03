"""Unit tests for PersonalMemoryService."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.memory import PersonalMemoryItem
from app.services.personal_memory_service import (
    PersonalMemoryService,
    PersonalMemoryServiceError,
)


def _make_memory_item(
    memory_id: str = "m1",
    memory: str = "Test memory",
    score: float | None = None,
    metadata: dict[str, object] | None = None,
) -> PersonalMemoryItem:
    """Factory for PersonalMemoryItem test data."""
    return PersonalMemoryItem(
        id=memory_id,
        memory=memory,
        score=score,
        metadata=metadata,
    )


class TestGetUserProfile:
    """Tests for PersonalMemoryService.get_user_profile."""

    async def test_profile_with_memories(self) -> None:
        """get_user_profile should build profile from memories."""
        svc = PersonalMemoryService()
        memories = [
            _make_memory_item("m1", "Kullanici kisa cevap tercih eder"),
            _make_memory_item("m2", "Her zaman sabah kontrol yapar"),
            _make_memory_item("m3", "Docker log detayli istiyor"),
        ]

        with patch(
            "app.services.personal_memory_service.memory_service"
        ) as mock_mem_svc:
            mock_mem_svc.get_all_personal_memories = AsyncMock(return_value=memories)
            profile = await svc.get_user_profile("user1")

        assert profile.user_id == "user1"
        assert profile.total_memories == 3
        assert isinstance(profile.preferences, dict)
        assert isinstance(profile.habits, list)
        # "Her zaman" is a habit indicator
        assert len(profile.habits) >= 1

    async def test_profile_empty_memories(self) -> None:
        """get_user_profile should return empty profile for no memories."""
        svc = PersonalMemoryService()

        with patch(
            "app.services.personal_memory_service.memory_service"
        ) as mock_mem_svc:
            mock_mem_svc.get_all_personal_memories = AsyncMock(return_value=[])
            profile = await svc.get_user_profile("user1")

        assert profile.user_id == "user1"
        assert profile.total_memories == 0
        assert profile.preferences == {}
        assert profile.habits == []
        assert profile.last_updated is None

    async def test_profile_service_error(self) -> None:
        """get_user_profile should raise PersonalMemoryServiceError."""
        svc = PersonalMemoryService()
        from app.services.memory_service import MemoryServiceError

        with patch(
            "app.services.personal_memory_service.memory_service"
        ) as mock_mem_svc:
            mock_mem_svc.get_all_personal_memories = AsyncMock(
                side_effect=MemoryServiceError("Connection failed", "get_all")
            )
            with pytest.raises(
                PersonalMemoryServiceError, match="Profil olusturulamadi"
            ):
                await svc.get_user_profile("user1")


class TestUpdateUserProfile:
    """Tests for PersonalMemoryService.update_user_profile."""

    async def test_update_preferences(self) -> None:
        """update_user_profile should save preferences as memories."""
        svc = PersonalMemoryService()
        mock_mem0 = MagicMock()
        mock_mem0.add.return_value = {"results": [{"id": "new_1"}]}

        with patch(
            "app.services.personal_memory_service.memory_service"
        ) as mock_mem_svc:
            mock_mem_svc._get_mem0.return_value = mock_mem0
            mock_mem_svc.get_all_personal_memories = AsyncMock(return_value=[])

            profile = await svc.update_user_profile(
                user_id="user1",
                preferences={"response_style": "kisa"},
            )

        assert profile.user_id == "user1"
        mock_mem0.add.assert_called_once()

    async def test_update_habits(self) -> None:
        """update_user_profile should save habits as memories."""
        svc = PersonalMemoryService()
        mock_mem0 = MagicMock()
        mock_mem0.add.return_value = {"results": []}

        with patch(
            "app.services.personal_memory_service.memory_service"
        ) as mock_mem_svc:
            mock_mem_svc._get_mem0.return_value = mock_mem0
            mock_mem_svc.get_all_personal_memories = AsyncMock(return_value=[])

            profile = await svc.update_user_profile(
                user_id="user1",
                habits=["Sabah kontrol", "Aksam deploy"],
            )

        assert profile.user_id == "user1"
        assert mock_mem0.add.call_count == 2  # One per habit

    async def test_update_error(self) -> None:
        """update_user_profile should raise on mem0 failure."""
        svc = PersonalMemoryService()
        mock_mem0 = MagicMock()
        mock_mem0.add.side_effect = RuntimeError("API error")

        with patch(
            "app.services.personal_memory_service.memory_service"
        ) as mock_mem_svc:
            mock_mem_svc._get_mem0.return_value = mock_mem0

            with pytest.raises(
                PersonalMemoryServiceError, match="Profil guncelleme basarisiz"
            ):
                await svc.update_user_profile(
                    user_id="user1",
                    preferences={"key": "val"},
                )


class TestExtractPersonalFacts:
    """Tests for PersonalMemoryService.extract_personal_facts."""

    async def test_extract_success(self) -> None:
        """extract_personal_facts should return extracted memory IDs."""
        svc = PersonalMemoryService()
        messages = [
            {"role": "user", "content": "Kisa cevap ver"},
            {"role": "assistant", "content": "Tamam"},
        ]

        with patch(
            "app.services.personal_memory_service.memory_service"
        ) as mock_mem_svc:
            mock_mem_svc.save_conversation_facts = AsyncMock(
                return_value=["fact_1", "fact_2"]
            )

            result = await svc.extract_personal_facts("user1", messages)

        assert result.total == 2
        assert "fact_1" in result.extracted_memories

    async def test_extract_empty(self) -> None:
        """extract_personal_facts should handle no facts extracted."""
        svc = PersonalMemoryService()

        with patch(
            "app.services.personal_memory_service.memory_service"
        ) as mock_mem_svc:
            mock_mem_svc.save_conversation_facts = AsyncMock(return_value=[])

            result = await svc.extract_personal_facts(
                "user1", [{"role": "user", "content": "Merhaba"}]
            )

        assert result.total == 0
        assert result.extracted_memories == []

    async def test_extract_error(self) -> None:
        """extract_personal_facts should raise on service failure."""
        svc = PersonalMemoryService()
        from app.services.memory_service import MemoryServiceError

        with patch(
            "app.services.personal_memory_service.memory_service"
        ) as mock_mem_svc:
            mock_mem_svc.save_conversation_facts = AsyncMock(
                side_effect=MemoryServiceError("Extraction failed", "save")
            )

            with pytest.raises(
                PersonalMemoryServiceError, match="Fact extraction basarisiz"
            ):
                await svc.extract_personal_facts(
                    "user1", [{"role": "user", "content": "test"}]
                )


class TestUpdateMemory:
    """Tests for PersonalMemoryService.update_memory."""

    async def test_update_success(self) -> None:
        """update_memory should return updated PersonalMemoryItem."""
        svc = PersonalMemoryService()
        mock_mem0 = MagicMock()
        mock_mem0.update.return_value = None

        with patch(
            "app.services.personal_memory_service.memory_service"
        ) as mock_mem_svc:
            mock_mem_svc._get_mem0.return_value = mock_mem0

            result = await svc.update_memory(
                "user1", "mem_123", "Updated memory content"
            )

        assert result.id == "mem_123"
        assert result.memory == "Updated memory content"
        mock_mem0.update.assert_called_once_with(
            memory_id="mem_123", data="Updated memory content"
        )

    async def test_update_error(self) -> None:
        """update_memory should raise on mem0 failure."""
        svc = PersonalMemoryService()
        mock_mem0 = MagicMock()
        mock_mem0.update.side_effect = RuntimeError("Not found")

        with patch(
            "app.services.personal_memory_service.memory_service"
        ) as mock_mem_svc:
            mock_mem_svc._get_mem0.return_value = mock_mem0

            with pytest.raises(
                PersonalMemoryServiceError, match="Hafiza guncelleme basarisiz"
            ):
                await svc.update_memory("user1", "mem_123", "new data")


class TestDeleteAllMemories:
    """Tests for PersonalMemoryService.delete_all_memories."""

    async def test_bulk_delete_success(self) -> None:
        """delete_all_memories should delete all and return count."""
        svc = PersonalMemoryService()
        memories = [
            _make_memory_item("m1", "Memory 1"),
            _make_memory_item("m2", "Memory 2"),
            _make_memory_item("m3", "Memory 3"),
        ]
        mock_mem0 = MagicMock()
        mock_mem0.delete.return_value = None

        with patch(
            "app.services.personal_memory_service.memory_service"
        ) as mock_mem_svc:
            mock_mem_svc.get_all_personal_memories = AsyncMock(return_value=memories)
            mock_mem_svc._get_mem0.return_value = mock_mem0

            result = await svc.delete_all_memories("user1")

        assert result.deleted_count == 3
        assert result.user_id == "user1"
        assert mock_mem0.delete.call_count == 3

    async def test_bulk_delete_empty(self) -> None:
        """delete_all_memories should handle no memories gracefully."""
        svc = PersonalMemoryService()

        with patch(
            "app.services.personal_memory_service.memory_service"
        ) as mock_mem_svc:
            mock_mem_svc.get_all_personal_memories = AsyncMock(return_value=[])
            mock_mem_svc._get_mem0.return_value = MagicMock()

            result = await svc.delete_all_memories("user1")

        assert result.deleted_count == 0
        assert result.user_id == "user1"

    async def test_bulk_delete_partial_failure(self) -> None:
        """delete_all_memories should continue on individual failures."""
        svc = PersonalMemoryService()
        memories = [
            _make_memory_item("m1", "Memory 1"),
            _make_memory_item("m2", "Memory 2"),
        ]
        mock_mem0 = MagicMock()
        # First succeeds, second fails
        mock_mem0.delete.side_effect = [None, RuntimeError("Failed")]

        with patch(
            "app.services.personal_memory_service.memory_service"
        ) as mock_mem_svc:
            mock_mem_svc.get_all_personal_memories = AsyncMock(return_value=memories)
            mock_mem_svc._get_mem0.return_value = mock_mem0

            result = await svc.delete_all_memories("user1")

        assert result.deleted_count == 1  # Only first succeeded

    async def test_bulk_delete_error(self) -> None:
        """delete_all_memories should raise on complete failure."""
        svc = PersonalMemoryService()
        from app.services.memory_service import MemoryServiceError

        with patch(
            "app.services.personal_memory_service.memory_service"
        ) as mock_mem_svc:
            mock_mem_svc.get_all_personal_memories = AsyncMock(
                side_effect=MemoryServiceError("Connection failed", "get_all")
            )

            with pytest.raises(
                PersonalMemoryServiceError, match="Toplu silme basarisiz"
            ):
                await svc.delete_all_memories("user1")


class TestGetStats:
    """Tests for PersonalMemoryService.get_stats."""

    async def test_stats_with_memories(self) -> None:
        """get_stats should return correct statistics."""
        svc = PersonalMemoryService()
        memories = [
            _make_memory_item(
                "m1",
                "Memory 1",
                metadata={"created_at": "2026-01-01T10:00:00"},
            ),
            _make_memory_item(
                "m2",
                "Memory 2",
                metadata={"created_at": "2026-03-01T15:00:00"},
            ),
        ]

        with patch(
            "app.services.personal_memory_service.memory_service"
        ) as mock_mem_svc:
            mock_mem_svc.get_all_personal_memories = AsyncMock(return_value=memories)
            stats = await svc.get_stats("user1")

        assert stats.user_id == "user1"
        assert stats.total_memories == 2
        assert stats.oldest_memory_date is not None
        assert stats.newest_memory_date is not None
        assert stats.oldest_memory_date < stats.newest_memory_date

    async def test_stats_empty(self) -> None:
        """get_stats should handle no memories."""
        svc = PersonalMemoryService()

        with patch(
            "app.services.personal_memory_service.memory_service"
        ) as mock_mem_svc:
            mock_mem_svc.get_all_personal_memories = AsyncMock(return_value=[])
            stats = await svc.get_stats("user1")

        assert stats.total_memories == 0
        assert stats.oldest_memory_date is None
        assert stats.newest_memory_date is None

    async def test_stats_no_metadata_dates(self) -> None:
        """get_stats should handle memories without date metadata."""
        svc = PersonalMemoryService()
        memories = [
            _make_memory_item("m1", "Memory 1"),
            _make_memory_item("m2", "Memory 2", metadata={"other": "value"}),
        ]

        with patch(
            "app.services.personal_memory_service.memory_service"
        ) as mock_mem_svc:
            mock_mem_svc.get_all_personal_memories = AsyncMock(return_value=memories)
            stats = await svc.get_stats("user1")

        assert stats.total_memories == 2
        assert stats.oldest_memory_date is None
        assert stats.newest_memory_date is None

    async def test_stats_error(self) -> None:
        """get_stats should raise on service failure."""
        svc = PersonalMemoryService()
        from app.services.memory_service import MemoryServiceError

        with patch(
            "app.services.personal_memory_service.memory_service"
        ) as mock_mem_svc:
            mock_mem_svc.get_all_personal_memories = AsyncMock(
                side_effect=MemoryServiceError("Error", "get_all")
            )
            with pytest.raises(
                PersonalMemoryServiceError, match="Istatistik alinamadi"
            ):
                await svc.get_stats("user1")


class TestExtractPreferences:
    """Tests for PersonalMemoryService._extract_preferences."""

    def test_detects_response_style(self) -> None:
        """Should detect response style preferences."""
        svc = PersonalMemoryService()
        memories = [_make_memory_item("m1", "Kisa cevap tercih eder")]
        prefs = svc._extract_preferences(memories)
        assert "response_style" in prefs

    def test_detects_workflow(self) -> None:
        """Should detect workflow preferences."""
        svc = PersonalMemoryService()
        memories = [_make_memory_item("m1", "Sabah ilk is proje durumu")]
        prefs = svc._extract_preferences(memories)
        assert "workflow" in prefs

    def test_empty_memories(self) -> None:
        """Should return empty dict for no memories."""
        svc = PersonalMemoryService()
        prefs = svc._extract_preferences([])
        assert prefs == {}

    def test_no_matching_keywords(self) -> None:
        """Should return empty dict if no keywords match."""
        svc = PersonalMemoryService()
        memories = [_make_memory_item("m1", "Random unrelated text")]
        prefs = svc._extract_preferences(memories)
        assert prefs == {}


class TestExtractHabits:
    """Tests for PersonalMemoryService._extract_habits."""

    def test_detects_habits(self) -> None:
        """Should detect habit indicators."""
        svc = PersonalMemoryService()
        memories = [
            _make_memory_item("m1", "Her zaman test sonuclarini kontrol eder"),
            _make_memory_item("m2", "Genellikle kisa cevap ister"),
        ]
        habits = svc._extract_habits(memories)
        assert len(habits) == 2

    def test_no_habits(self) -> None:
        """Should return empty list if no habit indicators."""
        svc = PersonalMemoryService()
        memories = [_make_memory_item("m1", "Random memory without indicators")]
        habits = svc._extract_habits(memories)
        assert habits == []

    def test_no_duplicates(self) -> None:
        """Should not add duplicate habits."""
        svc = PersonalMemoryService()
        memories = [
            _make_memory_item("m1", "Her zaman tercih eder kisa cevap"),
        ]
        habits = svc._extract_habits(memories)
        # Should appear only once even though "her zaman" and "tercih" both match
        assert len(habits) == 1
