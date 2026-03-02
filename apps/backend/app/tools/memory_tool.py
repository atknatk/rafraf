"""Memory Manager Tool - Claude AI tool for 3-layer memory operations.

Cloud tool that runs on EKS (no host agent required).
Provides memory search, save, update, and context building operations.
"""

import json
import uuid

import structlog

from app.core.database import async_session_factory
from app.orchestrator.tool_registry import ToolDefinition
from app.repositories.memory_repository import MemoryRepository
from app.services.memory_service import MemoryServiceError, memory_service
from app.tools.base import BaseTool

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

# Tool schema for Claude API
_MEMORY_TOOL_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": [
                "search_personal",
                "save_facts",
                "get_project_summary",
                "update_project_memory",
                "get_context",
                "get_all_personal",
                "delete_personal",
            ],
            "description": "Yapilacak hafiza islemi",
        },
        "user_id": {
            "type": "string",
            "description": "Kullanici ID'si (personal memory islemleri icin)",
        },
        "project_id": {
            "type": "string",
            "description": "Proje ID'si (project memory islemleri icin)",
        },
        "query": {
            "type": "string",
            "description": "Arama sorgusu (search_personal ve get_context icin)",
        },
        "session_id": {
            "type": "string",
            "description": "Oturum ID'si (save_facts ve get_context icin)",
        },
        "messages": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "role": {"type": "string"},
                    "content": {"type": "string"},
                },
            },
            "description": "Konusma mesajlari (save_facts icin)",
        },
        "category": {
            "type": "string",
            "description": "Hafiza kategorisi (update_project_memory icin)",
        },
        "key": {
            "type": "string",
            "description": "Hafiza anahtari (update_project_memory icin)",
        },
        "value": {
            "type": "object",
            "description": "Hafiza degeri (update_project_memory icin)",
        },
        "source": {
            "type": "string",
            "enum": ["user_stated", "ai_inferred", "tool_result"],
            "description": "Hafiza kaynagi (update_project_memory icin)",
            "default": "ai_inferred",
        },
        "memory_id": {
            "type": "string",
            "description": "Hafiza ID'si (delete_personal icin)",
        },
        "limit": {
            "type": "integer",
            "description": "Maksimum sonuc sayisi (search icin, varsayilan: 10)",
            "default": 10,
        },
    },
    "required": ["action"],
}


class MemoryTool(BaseTool):
    """Memory Manager tool for Claude AI.

    Provides 3-layer memory operations as a Claude tool. Registered with the
    tool registry and called by the AI orchestrator during tool-calling loops.
    This is a cloud tool (runs on EKS, no host agent required).
    """

    def get_definition(self) -> ToolDefinition:
        """Return the tool definition for Claude API.

        Returns:
            ToolDefinition with memory_manager schema.
        """
        return ToolDefinition(
            name="memory_manager",
            description=(
                "3-katmanli hafiza yonetimi. Kullanici hafizalari (personal, mem0 ile semantic "
                "search), proje hafizalari (project, PostgreSQL) ve konusma hafizalari "
                "(conversation, Redis) yonetir. Hafiza arama, kaydetme, guncelleme ve "
                "context olusturma islemleri yapar."
            ),
            input_schema=_MEMORY_TOOL_SCHEMA,
            requires_approval=False,
        )

    async def execute(self, params: dict[str, object]) -> str:
        """Execute a memory action.

        Args:
            params: Tool input parameters from Claude.

        Returns:
            JSON string result.
        """
        action = str(params.get("action", ""))
        if not action:
            return '{"error": "action parametresi zorunludur"}'

        await logger.ainfo("memory_tool_execute", action=action)

        try:
            return await self._dispatch(action, params)
        except MemoryServiceError as exc:
            await logger.aexception("memory_tool_error", action=action)
            return json.dumps({"error": f"Hafiza hatasi: {exc}"}, ensure_ascii=False)
        except Exception as exc:
            await logger.aexception("memory_tool_unexpected_error", action=action)
            return json.dumps({"error": f"Beklenmeyen hata: {exc}"}, ensure_ascii=False)

    async def _dispatch(self, action: str, params: dict[str, object]) -> str:
        """Dispatch to the appropriate action handler.

        Args:
            action: Action name.
            params: Full params dict.

        Returns:
            JSON string result.
        """
        if action == "search_personal":
            return await self._search_personal(params)
        if action == "save_facts":
            return await self._save_facts(params)
        if action == "get_project_summary":
            return await self._get_project_summary(params)
        if action == "update_project_memory":
            return await self._update_project_memory(params)
        if action == "get_context":
            return await self._get_context(params)
        if action == "get_all_personal":
            return await self._get_all_personal(params)
        if action == "delete_personal":
            return await self._delete_personal(params)
        return json.dumps({"error": f"Bilinmeyen action: {action}"}, ensure_ascii=False)

    async def _search_personal(self, params: dict[str, object]) -> str:
        user_id = str(params.get("user_id", ""))
        query = str(params.get("query", ""))
        if not user_id or not query:
            return '{"error": "user_id ve query parametreleri zorunludur"}'

        limit_raw = params.get("limit", 10)
        limit = int(limit_raw) if isinstance(limit_raw, (int, float)) else 10

        items = await memory_service.search_memories(user_id, query, limit=limit)
        result = {
            "memories": [
                {
                    "id": item.id,
                    "memory": item.memory,
                    "score": item.score,
                }
                for item in items
            ],
            "total": len(items),
        }
        return json.dumps(result, ensure_ascii=False)

    async def _save_facts(self, params: dict[str, object]) -> str:
        user_id = str(params.get("user_id", ""))
        session_id = str(params.get("session_id", ""))
        if not user_id or not session_id:
            return '{"error": "user_id ve session_id parametreleri zorunludur"}'

        messages_raw = params.get("messages", [])
        if not isinstance(messages_raw, list):
            return '{"error": "messages bir liste olmalidir"}'

        messages: list[dict[str, str]] = []
        for msg in messages_raw:
            if isinstance(msg, dict):
                messages.append(
                    {
                        "role": str(msg.get("role", "")),
                        "content": str(msg.get("content", "")),
                    }
                )

        memory_ids = await memory_service.save_conversation_facts(user_id, session_id, messages)
        return json.dumps(
            {"saved_memory_ids": memory_ids, "count": len(memory_ids)},
            ensure_ascii=False,
        )

    async def _get_project_summary(self, params: dict[str, object]) -> str:
        project_id_str = str(params.get("project_id", ""))
        if not project_id_str:
            return '{"error": "project_id parametresi zorunludur"}'

        try:
            project_id = uuid.UUID(project_id_str)
        except ValueError:
            return '{"error": "project_id gecerli bir UUID olmalidir"}'

        async with async_session_factory() as session:
            repo = MemoryRepository(session)
            summary = await memory_service.get_project_summary(repo, project_id)
            await session.commit()

        return json.dumps({"project_id": project_id_str, "summary": summary}, ensure_ascii=False)

    async def _update_project_memory(self, params: dict[str, object]) -> str:
        project_id_str = str(params.get("project_id", ""))
        category = str(params.get("category", ""))
        key = str(params.get("key", ""))
        value = params.get("value")

        if not project_id_str or not category or not key or value is None:
            return '{"error": "project_id, category, key ve value parametreleri zorunludur"}'

        if not isinstance(value, dict):
            return '{"error": "value bir dict olmalidir"}'

        try:
            project_id = uuid.UUID(project_id_str)
        except ValueError:
            return '{"error": "project_id gecerli bir UUID olmalidir"}'

        source = str(params.get("source", "ai_inferred"))

        async with async_session_factory() as session:
            repo = MemoryRepository(session)
            await memory_service.update_project_memory(
                repo,
                project_id=project_id,
                category=category,
                key=key,
                value=value,
                source=source,
            )
            await session.commit()

        return json.dumps(
            {
                "status": "updated",
                "project_id": project_id_str,
                "category": category,
                "key": key,
            },
            ensure_ascii=False,
        )

    async def _get_context(self, params: dict[str, object]) -> str:
        user_id = str(params.get("user_id", ""))
        query = str(params.get("query", ""))
        if not user_id or not query:
            return '{"error": "user_id ve query parametreleri zorunludur"}'

        project_id: uuid.UUID | None = None
        project_id_str = str(params.get("project_id", ""))
        if project_id_str:
            try:
                project_id = uuid.UUID(project_id_str)
            except ValueError:
                return '{"error": "project_id gecerli bir UUID olmalidir"}'

        session_id = str(params.get("session_id", "")) or None

        async with async_session_factory() as session:
            repo = MemoryRepository(session)
            context = await memory_service.get_context_for_message(
                repo,
                user_id=user_id,
                message=query,
                project_id=project_id,
                session_id=session_id,
            )
            await session.commit()

        return json.dumps(
            {
                "personal_memories": context.personal_memories,
                "project_summary": context.project_summary,
                "conversation_summary": context.conversation_summary,
                "token_count": context.token_count,
            },
            ensure_ascii=False,
        )

    async def _get_all_personal(self, params: dict[str, object]) -> str:
        user_id = str(params.get("user_id", ""))
        if not user_id:
            return '{"error": "user_id parametresi zorunludur"}'

        items = await memory_service.get_all_personal_memories(user_id)
        result = {
            "memories": [
                {
                    "id": item.id,
                    "memory": item.memory,
                    "metadata": item.metadata,
                }
                for item in items
            ],
            "total": len(items),
        }
        return json.dumps(result, ensure_ascii=False)

    async def _delete_personal(self, params: dict[str, object]) -> str:
        memory_id = str(params.get("memory_id", ""))
        if not memory_id:
            return '{"error": "memory_id parametresi zorunludur"}'

        await memory_service.delete_personal_memory(memory_id)
        return json.dumps({"status": "deleted", "memory_id": memory_id}, ensure_ascii=False)
