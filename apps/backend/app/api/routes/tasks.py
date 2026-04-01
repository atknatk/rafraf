"""REST endpoints for task management."""

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status
from starlette.responses import JSONResponse

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.task import (
    LiveActivityTokenRequest,
    TaskCreate,
    TaskListResponse,
    TaskResponse,
)
from app.services.task_orchestrator_service import TaskOrchestratorService

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


def _task_to_response(task: object) -> dict[str, str | int | None]:
    """Convert a task model/mock to a response dict."""
    return {
        "id": str(getattr(task, "id", "")),
        "user_id": str(getattr(task, "user_id", "")),
        "project_id": str(task.project_id) if getattr(task, "project_id", None) else None,
        "agent_id": getattr(task, "agent_id", None),
        "title": getattr(task, "title", ""),
        "prompt": getattr(task, "prompt", ""),
        "task_type": getattr(task, "task_type", "feature"),
        "status": _status_value(getattr(task, "status", "queued")),
        "current_step": getattr(task, "current_step", None),
        "total_steps": getattr(task, "total_steps", 4),
        "completed_steps": getattr(task, "completed_steps", 0),
        "progress_pct": getattr(task, "progress_pct", 0),
        "result_summary": getattr(task, "result_summary", None),
        "error_message": getattr(task, "error_message", None),
        "claude_session_id": getattr(task, "claude_session_id", None),
        "claude_task_id": getattr(task, "claude_task_id", None),
        "has_live_activity_token": getattr(task, "live_activity_push_token", None) is not None,
        "created_at": _to_str(getattr(task, "created_at", None)),
        "started_at": _to_str(getattr(task, "started_at", None)),
        "completed_at": _to_str(getattr(task, "completed_at", None)),
        "updated_at": _to_str(getattr(task, "updated_at", None)),
    }


def _status_value(status_val: object) -> str:
    """Extract string value from status (handles enum or str)."""
    if hasattr(status_val, "value"):
        return str(status_val.value)
    return str(status_val)


def _to_str(val: object) -> str | None:
    """Convert a value to string or None."""
    if val is None:
        return None
    return str(val)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_task(
    body: TaskCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> JSONResponse:
    """Create a new AI task."""
    service = TaskOrchestratorService(session)
    task = await service.create_task(
        user_id=current_user.id,
        project_id=body.project_id,
        prompt=body.prompt,
        task_type=body.task_type,
    )
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=_task_to_response(task),
    )


@router.get("/active")
async def get_active_tasks(
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[dict[str, str | int | None]]:
    """Return active (non-terminal) tasks for the current user."""
    service = TaskOrchestratorService(session)
    tasks = await service.get_active_tasks(current_user.id)
    return [_task_to_response(t) for t in tasks]


@router.get("/history")
async def get_task_history(
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict[str, list[dict[str, str | int | None]] | int]:
    """Return paginated history of completed/failed/cancelled tasks."""
    service = TaskOrchestratorService(session)
    result = await service.get_task_history(current_user.id, page=page, page_size=size)
    tasks_raw = result.get("tasks", [])
    tasks_list: list[object] = tasks_raw if isinstance(tasks_raw, list) else []
    return {
        "tasks": [_task_to_response(t) for t in tasks_list],
        "total": result.get("total", 0),
        "page": result.get("page", page),
        "page_size": result.get("page_size", size),
    }


@router.get("/{task_id}")
async def get_task_detail(
    task_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> JSONResponse:
    """Return detail for a specific task."""
    service = TaskOrchestratorService(session)
    task = await service.get_task(task_id)
    if task is None:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": "Task not found"},
        )
    if str(task.user_id) != str(current_user.id):
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": "Forbidden"},
        )
    return JSONResponse(content=_task_to_response(task))


@router.post("/{task_id}/cancel")
async def cancel_task(
    task_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> JSONResponse:
    """Cancel an active task."""
    service = TaskOrchestratorService(session)
    existing = await service.get_task(task_id)
    if existing is None:
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": "Task not found"})
    if str(existing.user_id) != str(current_user.id):
        return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content={"detail": "Forbidden"})
    try:
        task = await service.cancel_task(task_id)
    except ValueError as exc:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": str(exc)},
        )
    return JSONResponse(content=_task_to_response(task))


@router.patch("/{task_id}/live-activity")
async def register_live_activity_token(
    task_id: uuid.UUID,
    body: LiveActivityTokenRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> JSONResponse:
    """Register an APNs push token for Live Activity updates."""
    service = TaskOrchestratorService(session)
    existing = await service.get_task(task_id)
    if existing is None:
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": "Task not found"})
    if str(existing.user_id) != str(current_user.id):
        return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content={"detail": "Forbidden"})
    try:
        task = await service.register_live_activity_token(
            task_id=task_id,
            token=body.push_token,
        )
    except ValueError as exc:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": str(exc)},
        )
    return JSONResponse(content=_task_to_response(task))
