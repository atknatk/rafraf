"""REST endpoints for memory manager (admin/debug operations)."""

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.api.deps import get_db
from app.core.exceptions import NotFoundError
from app.repositories.memory_repository import MemoryRepository
from app.schemas.memory import (
    MemoryContextResponse,
    PersonalMemoryItem,
    PersonalMemoryListResponse,
    ProjectMemoryCreateRequest,
    ProjectMemoryListResponse,
    ProjectMemoryResponse,
)
from app.services.memory_service import memory_service

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/memory", tags=["memory"])


# --- Project Memory Endpoints ---


@router.get("/project/{project_id}", response_model=ProjectMemoryListResponse)
async def list_project_memories(
    project_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    category: Annotated[str | None, Query(max_length=50, description="Kategori filtresi")] = None,
    key: Annotated[str | None, Query(max_length=100, description="Anahtar filtresi")] = None,
) -> ProjectMemoryListResponse:
    """List project memories with optional category/key filter."""
    repo = MemoryRepository(session)
    rows = await repo.list_by_project(project_id, category=category, key=key)
    items = [
        ProjectMemoryResponse(
            id=row.id,
            project_id=row.project_id,
            category=row.category,
            key=row.key,
            value=row.value,
            confidence=row.confidence,
            source=row.source,
            last_verified_at=None,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        for row in rows
    ]
    return ProjectMemoryListResponse(items=items, total=len(items))


@router.post(
    "/project/{project_id}",
    response_model=ProjectMemoryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_or_update_project_memory(
    project_id: uuid.UUID,
    body: ProjectMemoryCreateRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ProjectMemoryResponse:
    """Create or update a project memory entry (UPSERT)."""
    repo = MemoryRepository(session)
    row = await repo.upsert(
        project_id=project_id,
        category=body.category,
        key=body.key,
        value=body.value,
        confidence=body.confidence,
        source=body.source,
    )
    return ProjectMemoryResponse(
        id=row.id,
        project_id=row.project_id,
        category=row.category,
        key=row.key,
        value=row.value,
        confidence=row.confidence,
        source=row.source,
        last_verified_at=None,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.delete(
    "/project/{project_id}/{memory_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_project_memory(
    project_id: uuid.UUID,
    memory_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete a project memory entry."""
    repo = MemoryRepository(session)
    deleted = await repo.delete_by_id(memory_id, project_id)
    if not deleted:
        raise NotFoundError(message=f"Memory '{memory_id}' not found")


# --- Personal Memory Endpoints ---


@router.get("/personal/{user_id}", response_model=PersonalMemoryListResponse)
async def search_personal_memories(
    user_id: str,
    query: Annotated[str | None, Query(description="Arama sorgusu (semantic search)")] = None,
    limit: Annotated[int, Query(ge=1, le=50, description="Maksimum sonuc sayisi")] = 10,
) -> PersonalMemoryListResponse:
    """Search or list personal memories for a user."""
    if query:
        items = await memory_service.search_memories(user_id, query, limit=limit)
    else:
        items = await memory_service.get_all_personal_memories(user_id)
        items = items[:limit]
    return PersonalMemoryListResponse(
        items=[
            PersonalMemoryItem(
                id=item.id,
                memory=item.memory,
                score=item.score,
                metadata=item.metadata,
            )
            for item in items
        ],
        total=len(items),
    )


@router.delete(
    "/personal/{user_id}/{memory_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_personal_memory(
    user_id: str,
    memory_id: str,
) -> None:
    """Delete a personal memory from mem0."""
    await logger.ainfo("delete_personal_memory", user_id=user_id, memory_id=memory_id)
    await memory_service.delete_personal_memory(memory_id)


# --- Context Endpoint ---


@router.get("/context/{user_id}", response_model=MemoryContextResponse)
async def get_memory_context(
    user_id: str,
    session: Annotated[AsyncSession, Depends(get_db)],
    message: Annotated[str, Query(min_length=1, description="Kullanici mesaji")],
    project_id: Annotated[uuid.UUID | None, Query(description="Opsiyonel proje ID")] = None,
) -> MemoryContextResponse:
    """Build full memory context for a message (personal + project + conversation)."""
    repo = MemoryRepository(session)
    context = await memory_service.get_context_for_message(
        repo,
        user_id=user_id,
        message=message,
        project_id=project_id,
    )
    return MemoryContextResponse(
        personal_memories=context.personal_memories,
        project_summary=context.project_summary,
        conversation_summary=context.conversation_summary,
        token_count=context.token_count,
    )
