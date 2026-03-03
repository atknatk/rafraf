"""Unit tests for personal memory Pydantic schemas."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas.personal_memory import (
    BulkDeleteResponse,
    PersonalFactExtractionRequest,
    PersonalFactExtractionResponse,
    PersonalMemoryStatsResponse,
    PersonalMemoryUpdateRequest,
    UserProfile,
    UserProfileUpdateRequest,
)


class TestUserProfile:
    """Tests for UserProfile schema."""

    def test_valid_profile(self) -> None:
        """UserProfile should accept valid data."""
        profile = UserProfile(
            user_id="user1",
            preferences={"style": "kisa"},
            habits=["sabah kontrol"],
            total_memories=5,
            last_updated=datetime.now(tz=UTC),
        )
        assert profile.user_id == "user1"
        assert profile.total_memories == 5

    def test_frozen(self) -> None:
        """UserProfile should be immutable."""
        profile = UserProfile(
            user_id="user1",
            preferences={},
            habits=[],
            total_memories=0,
            last_updated=None,
        )
        with pytest.raises(ValidationError):
            profile.user_id = "user2"  # type: ignore[misc]

    def test_null_last_updated(self) -> None:
        """UserProfile should accept None for last_updated."""
        profile = UserProfile(
            user_id="user1",
            preferences={},
            habits=[],
            total_memories=0,
            last_updated=None,
        )
        assert profile.last_updated is None


class TestUserProfileUpdateRequest:
    """Tests for UserProfileUpdateRequest schema."""

    def test_valid_request(self) -> None:
        """Should accept valid preferences and habits."""
        req = UserProfileUpdateRequest(
            preferences={"lang": "tr"},
            habits=["sabah", "aksam"],
        )
        assert req.preferences == {"lang": "tr"}
        assert len(req.habits) == 2

    def test_empty_request(self) -> None:
        """Should accept empty (all None) request."""
        req = UserProfileUpdateRequest()
        assert req.preferences is None
        assert req.habits is None

    def test_partial_request(self) -> None:
        """Should accept only preferences without habits."""
        req = UserProfileUpdateRequest(preferences={"key": "val"})
        assert req.preferences is not None
        assert req.habits is None


class TestPersonalFactExtractionRequest:
    """Tests for PersonalFactExtractionRequest schema."""

    def test_valid_request(self) -> None:
        """Should accept valid messages list."""
        req = PersonalFactExtractionRequest(
            messages=[{"role": "user", "content": "Hello"}]
        )
        assert len(req.messages) == 1

    def test_empty_messages_rejected(self) -> None:
        """Should reject empty messages list."""
        with pytest.raises(ValidationError):
            PersonalFactExtractionRequest(messages=[])


class TestPersonalMemoryUpdateRequest:
    """Tests for PersonalMemoryUpdateRequest schema."""

    def test_valid_request(self) -> None:
        """Should accept valid data."""
        req = PersonalMemoryUpdateRequest(data="Updated content")
        assert req.data == "Updated content"

    def test_empty_data_rejected(self) -> None:
        """Should reject empty data."""
        with pytest.raises(ValidationError):
            PersonalMemoryUpdateRequest(data="")

    def test_max_length(self) -> None:
        """Should reject data longer than 4096 chars."""
        with pytest.raises(ValidationError):
            PersonalMemoryUpdateRequest(data="x" * 4097)


class TestBulkDeleteResponse:
    """Tests for BulkDeleteResponse schema."""

    def test_valid_response(self) -> None:
        """Should accept valid response data."""
        resp = BulkDeleteResponse(deleted_count=5, user_id="user1")
        assert resp.deleted_count == 5
        assert resp.user_id == "user1"

    def test_frozen(self) -> None:
        """Should be immutable."""
        resp = BulkDeleteResponse(deleted_count=0, user_id="user1")
        with pytest.raises(ValidationError):
            resp.deleted_count = 10  # type: ignore[misc]


class TestPersonalMemoryStatsResponse:
    """Tests for PersonalMemoryStatsResponse schema."""

    def test_valid_stats(self) -> None:
        """Should accept valid stats."""
        now = datetime.now(tz=UTC)
        stats = PersonalMemoryStatsResponse(
            user_id="user1",
            total_memories=10,
            oldest_memory_date=now,
            newest_memory_date=now,
        )
        assert stats.total_memories == 10

    def test_null_dates(self) -> None:
        """Should accept None dates."""
        stats = PersonalMemoryStatsResponse(
            user_id="user1",
            total_memories=0,
            oldest_memory_date=None,
            newest_memory_date=None,
        )
        assert stats.oldest_memory_date is None


class TestPersonalFactExtractionResponse:
    """Tests for PersonalFactExtractionResponse schema."""

    def test_valid_response(self) -> None:
        """Should accept valid extraction response."""
        resp = PersonalFactExtractionResponse(
            extracted_memories=["id1", "id2"],
            total=2,
        )
        assert resp.total == 2
        assert len(resp.extracted_memories) == 2

    def test_empty_extraction(self) -> None:
        """Should accept empty extraction."""
        resp = PersonalFactExtractionResponse(
            extracted_memories=[],
            total=0,
        )
        assert resp.total == 0

    def test_frozen(self) -> None:
        """Should be immutable."""
        resp = PersonalFactExtractionResponse(
            extracted_memories=[],
            total=0,
        )
        with pytest.raises(ValidationError):
            resp.total = 5  # type: ignore[misc]
