"""Personal memory service - user profile, fact extraction, privacy controls.

Extends the base MemoryService with higher-level personal memory operations
including user profile building, conversation-based fact extraction,
memory update, bulk deletion (privacy), and statistics.
"""

from datetime import datetime

import structlog

from app.schemas.memory import PersonalMemoryItem
from app.schemas.personal_memory import (
    BulkDeleteResponse,
    PersonalFactExtractionResponse,
    PersonalMemoryStatsResponse,
    UserProfile,
)
from app.services.memory_service import MemoryServiceError, memory_service

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

# Preference categories detected by keyword analysis
_PREFERENCE_KEYWORDS: dict[str, list[str]] = {
    "response_style": ["kisa", "detayli", "ozet", "aciklayici", "kisaca"],
    "language": ["turkce", "ingilizce", "english", "turkish"],
    "output_format": ["json", "tablo", "liste", "markdown", "kod"],
    "notification": ["bildirim", "uyari", "hatirlatma", "notification"],
    "workflow": ["sabah", "aksam", "sprint", "daily", "deploy"],
}


class PersonalMemoryServiceError(Exception):
    """Raised when a personal memory operation fails."""

    def __init__(self, message: str, operation: str = "") -> None:
        self.operation = operation
        super().__init__(message)


class PersonalMemoryService:
    """High-level personal memory operations.

    Builds user profiles from mem0 memories, performs conversation-based
    fact extraction, provides privacy controls (bulk delete), and
    computes memory statistics.
    """

    async def get_user_profile(self, user_id: str) -> UserProfile:
        """Build a dynamic user profile from personal memories.

        Analyzes all memories to extract preferences and habits.

        Args:
            user_id: User identifier.

        Returns:
            UserProfile with preferences, habits, and totals.
        """
        try:
            all_memories = await memory_service.get_all_personal_memories(user_id)
        except MemoryServiceError as exc:
            raise PersonalMemoryServiceError(
                f"Profil olusturulamadi: {exc}",
                operation="get_user_profile",
            ) from exc

        preferences = self._extract_preferences(all_memories)
        habits = self._extract_habits(all_memories)
        last_updated = self._get_latest_date(all_memories)

        await logger.ainfo(
            "user_profile_built",
            user_id=user_id,
            total_memories=len(all_memories),
            preference_count=len(preferences),
            habit_count=len(habits),
        )

        return UserProfile(
            user_id=user_id,
            preferences=preferences,
            habits=habits,
            total_memories=len(all_memories),
            last_updated=last_updated,
        )

    async def update_user_profile(
        self,
        user_id: str,
        preferences: dict[str, object] | None = None,
        habits: list[str] | None = None,
    ) -> UserProfile:
        """Update user profile by saving preferences/habits as memories.

        Each preference/habit is saved as a separate memory in mem0.

        Args:
            user_id: User identifier.
            preferences: Optional preferences dict to save.
            habits: Optional habits list to save.

        Returns:
            Updated UserProfile.
        """
        mem0 = memory_service._get_mem0()

        try:
            if preferences:
                for pref_key, pref_value in preferences.items():
                    mem0.add(  # type: ignore[attr-defined]
                        messages=[
                            {
                                "role": "user",
                                "content": f"Tercihim: {pref_key} = {pref_value}",
                            }
                        ],
                        user_id=user_id,
                        metadata={"type": "preference", "key": pref_key},
                    )

            if habits:
                for habit in habits:
                    mem0.add(  # type: ignore[attr-defined]
                        messages=[
                            {
                                "role": "user",
                                "content": f"Aliskanligim: {habit}",
                            }
                        ],
                        user_id=user_id,
                        metadata={"type": "habit"},
                    )

            await logger.ainfo(
                "user_profile_updated",
                user_id=user_id,
                preferences_count=len(preferences) if preferences else 0,
                habits_count=len(habits) if habits else 0,
            )
        except Exception as exc:
            raise PersonalMemoryServiceError(
                f"Profil guncelleme basarisiz: {exc}",
                operation="update_user_profile",
            ) from exc

        return await self.get_user_profile(user_id)

    async def extract_personal_facts(
        self,
        user_id: str,
        messages: list[dict[str, str]],
    ) -> PersonalFactExtractionResponse:
        """Extract personal facts from conversation and save to mem0.

        Uses mem0's built-in fact extraction (via mem0.add).

        Args:
            user_id: User identifier.
            messages: Conversation messages to analyze.

        Returns:
            PersonalFactExtractionResponse with extracted memory IDs.
        """
        await logger.ainfo(
            "personal_fact_extraction_started",
            user_id=user_id,
            message_count=len(messages),
        )

        try:
            memory_ids = await memory_service.save_conversation_facts(
                user_id=user_id,
                session_id=f"extract-{user_id}",
                messages=messages,
            )

            await logger.ainfo(
                "personal_fact_extraction_completed",
                user_id=user_id,
                extracted_count=len(memory_ids),
            )

            return PersonalFactExtractionResponse(
                extracted_memories=memory_ids,
                total=len(memory_ids),
            )
        except MemoryServiceError as exc:
            raise PersonalMemoryServiceError(
                f"Fact extraction basarisiz: {exc}",
                operation="extract_personal_facts",
            ) from exc

    async def update_memory(
        self,
        user_id: str,
        memory_id: str,
        data: str,
    ) -> PersonalMemoryItem:
        """Update a single personal memory in mem0.

        Args:
            user_id: User identifier (for logging/audit).
            memory_id: mem0 memory ID.
            data: New memory content.

        Returns:
            Updated PersonalMemoryItem.
        """
        mem0 = memory_service._get_mem0()

        try:
            mem0.update(memory_id=memory_id, data=data)  # type: ignore[attr-defined]

            await logger.ainfo(
                "personal_memory_updated",
                user_id=user_id,
                memory_id=memory_id,
            )

            return PersonalMemoryItem(
                id=memory_id,
                memory=data,
                score=None,
                metadata=None,
            )
        except Exception as exc:
            raise PersonalMemoryServiceError(
                f"Hafiza guncelleme basarisiz: {exc}",
                operation="update_memory",
            ) from exc

    async def delete_all_memories(self, user_id: str) -> BulkDeleteResponse:
        """Delete all personal memories for a user (right to be forgotten).

        This operation is irreversible.

        Args:
            user_id: User identifier.

        Returns:
            BulkDeleteResponse with deletion count.
        """
        await logger.awarning(
            "bulk_delete_initiated",
            user_id=user_id,
        )

        try:
            all_memories = await memory_service.get_all_personal_memories(user_id)
            deleted_count = 0

            mem0 = memory_service._get_mem0()
            for item in all_memories:
                try:
                    mem0.delete(memory_id=item.id)  # type: ignore[attr-defined]
                    deleted_count += 1
                except Exception:
                    await logger.awarning(
                        "single_memory_delete_failed",
                        user_id=user_id,
                        memory_id=item.id,
                    )

            await logger.ainfo(
                "bulk_delete_completed",
                user_id=user_id,
                deleted_count=deleted_count,
                total_attempted=len(all_memories),
            )

            return BulkDeleteResponse(
                deleted_count=deleted_count,
                user_id=user_id,
            )
        except MemoryServiceError as exc:
            raise PersonalMemoryServiceError(
                f"Toplu silme basarisiz: {exc}",
                operation="delete_all_memories",
            ) from exc

    async def get_stats(self, user_id: str) -> PersonalMemoryStatsResponse:
        """Get personal memory statistics for a user.

        Args:
            user_id: User identifier.

        Returns:
            PersonalMemoryStatsResponse with counts and dates.
        """
        try:
            all_memories = await memory_service.get_all_personal_memories(user_id)
        except MemoryServiceError as exc:
            raise PersonalMemoryServiceError(
                f"Istatistik alinamadi: {exc}",
                operation="get_stats",
            ) from exc

        oldest_date: datetime | None = None
        newest_date: datetime | None = None

        for item in all_memories:
            if item.metadata and "created_at" in item.metadata:
                try:
                    created = datetime.fromisoformat(str(item.metadata["created_at"]))
                    if oldest_date is None or created < oldest_date:
                        oldest_date = created
                    if newest_date is None or created > newest_date:
                        newest_date = created
                except (ValueError, TypeError):
                    continue

        return PersonalMemoryStatsResponse(
            user_id=user_id,
            total_memories=len(all_memories),
            oldest_memory_date=oldest_date,
            newest_memory_date=newest_date,
        )

    def _extract_preferences(
        self,
        memories: list[PersonalMemoryItem],
    ) -> dict[str, object]:
        """Extract user preferences from memory texts.

        Scans memory content for known preference keywords and categorizes them.

        Args:
            memories: List of personal memories.

        Returns:
            Dict of preference categories with detected values.
        """
        preferences: dict[str, object] = {}

        for memory_item in memories:
            text = memory_item.memory.lower()
            for category, keywords in _PREFERENCE_KEYWORDS.items():
                for keyword in keywords:
                    if keyword in text:
                        if category not in preferences:
                            preferences[category] = []
                        if isinstance(preferences[category], list):
                            pref_list: list[str] = preferences[category]  # type: ignore[assignment]
                            if memory_item.memory not in pref_list:
                                pref_list.append(memory_item.memory)
                        break

        return preferences

    def _extract_habits(
        self,
        memories: list[PersonalMemoryItem],
    ) -> list[str]:
        """Extract habit-like patterns from memory texts.

        Looks for memories containing habit indicators.

        Args:
            memories: List of personal memories.

        Returns:
            List of habit descriptions.
        """
        habit_indicators = [
            "her zaman",
            "genellikle",
            "tercih",
            "aliskanl",
            "rutin",
            "sabah",
            "aksam",
            "ilk is",
            "son is",
            "always",
            "usually",
            "prefer",
        ]
        habits: list[str] = []

        for memory_item in memories:
            text = memory_item.memory.lower()
            for indicator in habit_indicators:
                if indicator in text:
                    if memory_item.memory not in habits:
                        habits.append(memory_item.memory)
                    break

        return habits

    def _get_latest_date(
        self,
        memories: list[PersonalMemoryItem],
    ) -> datetime | None:
        """Get the most recent created_at date from memories.

        Args:
            memories: List of personal memories.

        Returns:
            Most recent datetime or None.
        """
        latest: datetime | None = None

        for item in memories:
            if item.metadata and "created_at" in item.metadata:
                try:
                    created = datetime.fromisoformat(str(item.metadata["created_at"]))
                    if latest is None or created > latest:
                        latest = created
                except (ValueError, TypeError):
                    continue

        return latest


# Module-level singleton
personal_memory_service = PersonalMemoryService()
