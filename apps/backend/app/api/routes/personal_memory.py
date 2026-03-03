"""REST endpoints for personal memory (mem0 + pgvector).

Provides user profile, fact extraction, memory update, bulk delete (privacy),
and statistics endpoints for personal memory management.
"""

import structlog
from fastapi import APIRouter

from app.schemas.memory import PersonalMemoryItem
from app.schemas.personal_memory import (
    BulkDeleteResponse,
    PersonalFactExtractionRequest,
    PersonalFactExtractionResponse,
    PersonalMemoryStatsResponse,
    PersonalMemoryUpdateRequest,
    UserProfile,
    UserProfileUpdateRequest,
)
from app.services.personal_memory_service import personal_memory_service

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/personal-memory", tags=["personal-memory"])


# --- Profile Endpoints ---


@router.get("/{user_id}/profile", response_model=UserProfile)
async def get_user_profile(user_id: str) -> UserProfile:
    """Get user profile built from personal memories.

    Dynamically builds profile from all mem0 memories for the user,
    extracting preferences and habits.
    """
    return await personal_memory_service.get_user_profile(user_id)


@router.put("/{user_id}/profile", response_model=UserProfile)
async def update_user_profile(
    user_id: str,
    body: UserProfileUpdateRequest,
) -> UserProfile:
    """Update user profile preferences and habits.

    Saves each preference/habit as a separate memory in mem0.
    """
    return await personal_memory_service.update_user_profile(
        user_id=user_id,
        preferences=body.preferences,
        habits=body.habits,
    )


# --- Fact Extraction ---


@router.post(
    "/{user_id}/extract",
    response_model=PersonalFactExtractionResponse,
)
async def extract_personal_facts(
    user_id: str,
    body: PersonalFactExtractionRequest,
) -> PersonalFactExtractionResponse:
    """Extract personal facts from conversation messages.

    Uses mem0's built-in fact extraction to identify and save
    user preferences, habits, and personal information.
    """
    return await personal_memory_service.extract_personal_facts(
        user_id=user_id,
        messages=body.messages,
    )


# --- Memory Update ---


@router.put(
    "/{user_id}/memories/{memory_id}",
    response_model=PersonalMemoryItem,
)
async def update_personal_memory(
    user_id: str,
    memory_id: str,
    body: PersonalMemoryUpdateRequest,
) -> PersonalMemoryItem:
    """Update a single personal memory in mem0."""
    return await personal_memory_service.update_memory(
        user_id=user_id,
        memory_id=memory_id,
        data=body.data,
    )


# --- Privacy / Bulk Delete ---


@router.delete(
    "/{user_id}/all",
    response_model=BulkDeleteResponse,
)
async def delete_all_personal_memories(
    user_id: str,
) -> BulkDeleteResponse:
    """Delete all personal memories for a user (right to be forgotten).

    This operation is irreversible. All memories stored in mem0 for
    this user will be permanently deleted.
    """
    return await personal_memory_service.delete_all_memories(user_id)


# --- Statistics ---


@router.get(
    "/{user_id}/stats",
    response_model=PersonalMemoryStatsResponse,
)
async def get_personal_memory_stats(
    user_id: str,
) -> PersonalMemoryStatsResponse:
    """Get personal memory statistics for a user."""
    return await personal_memory_service.get_stats(user_id)
