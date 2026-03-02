"""Memory service - 3-layer memory system (conversation, project, personal).

Conversation Memory: Redis (short-lived, per-session).
Project Memory: PostgreSQL via MemoryRepository (structured, per-project).
Personal Memory: mem0 + pgvector (semantic search, per-user).
"""

import json
import uuid

import structlog

from app.core.config import get_settings
from app.core.redis import redis_client
from app.repositories.memory_repository import MemoryRepository
from app.schemas.memory import (
    MemoryContext,
    PersonalMemoryItem,
)

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

# Token budget limits for context building
_PERSONAL_TOKEN_BUDGET = 1500
_PROJECT_TOKEN_BUDGET = 1000
_CONVERSATION_SUMMARY_TOKEN_BUDGET = 500

# Rough estimate: 1 token ~ 4 characters
_CHARS_PER_TOKEN = 4

# Similarity threshold for personal memory search
_SIMILARITY_THRESHOLD = 0.60


class MemoryServiceError(Exception):
    """Raised when a memory operation fails."""

    def __init__(self, message: str, operation: str = "") -> None:
        self.operation = operation
        super().__init__(message)


class MemoryService:
    """Three-layer memory management service.

    Coordinates conversation memory (Redis), project memory (PostgreSQL),
    and personal memory (mem0 + pgvector) to build AI context.
    """

    def __init__(self) -> None:
        self._mem0_client: object | None = None
        self._mem0_initialized = False

    def _get_mem0(self) -> object:
        """Lazily initialize the mem0 client.

        Returns:
            Configured mem0 Memory instance.

        Raises:
            MemoryServiceError: If mem0 cannot be initialized.
        """
        if self._mem0_client is not None:
            return self._mem0_client

        try:
            from mem0 import Memory

            settings = get_settings()
            config: dict[str, object] = {
                "vector_store": {
                    "provider": "pgvector",
                    "config": {
                        "connection_string": settings.database_url.replace(
                            "postgresql+asyncpg://", "postgresql://"
                        ),
                        "collection_name": "memories",
                        "embedding_model_dims": 1536,
                    },
                },
                "embedder": {
                    "provider": "openai",
                    "config": {
                        "model": "text-embedding-3-small",
                        "api_key": settings.openai_api_key,
                    },
                },
                "llm": {
                    "provider": "anthropic",
                    "config": {
                        "model": "claude-haiku-4-5-20251001",
                        "api_key": settings.anthropic_api_key,
                    },
                },
            }
            self._mem0_client = Memory.from_config(config)
            self._mem0_initialized = True
            return self._mem0_client
        except Exception as exc:
            raise MemoryServiceError(
                f"mem0 baslatilamadi: {exc}",
                operation="init_mem0",
            ) from exc

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count from character length.

        Args:
            text: Input text.

        Returns:
            Estimated token count.
        """
        return len(text) // _CHARS_PER_TOKEN

    def _truncate_to_budget(self, text: str, budget: int) -> str:
        """Truncate text to fit within a token budget.

        Args:
            text: Input text.
            budget: Maximum tokens.

        Returns:
            Truncated text.
        """
        max_chars = budget * _CHARS_PER_TOKEN
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + "..."

    # --- Layer 1: Conversation Memory (Redis) ---

    async def save_conversation(
        self,
        session_id: str,
        messages: list[dict[str, str]],
        ttl: int = 7200,
    ) -> None:
        """Save conversation messages to Redis.

        Args:
            session_id: Session identifier.
            messages: Conversation message list.
            ttl: Time-to-live in seconds.
        """
        await redis_client.save_conversation(session_id, messages, ttl=ttl)
        await logger.ainfo(
            "conversation_saved",
            session_id=session_id,
            message_count=len(messages),
        )

    async def get_conversation(self, session_id: str) -> list[dict[str, str]]:
        """Retrieve conversation messages from Redis.

        Args:
            session_id: Session identifier.

        Returns:
            List of conversation messages.
        """
        return await redis_client.get_conversation(session_id)

    async def append_message(
        self,
        session_id: str,
        message: dict[str, str],
    ) -> None:
        """Append a message to the conversation.

        Args:
            session_id: Session identifier.
            message: Message dict with role and content.
        """
        await redis_client.append_message(session_id, message)

    async def clear_conversation(self, session_id: str) -> bool:
        """Clear conversation cache for a session.

        Args:
            session_id: Session identifier.

        Returns:
            True if deleted.
        """
        return await redis_client.delete_conversation(session_id)

    # --- Layer 2: Project Memory (PostgreSQL) ---

    async def update_project_memory(
        self,
        repo: MemoryRepository,
        project_id: uuid.UUID,
        category: str,
        key: str,
        value: dict[str, object],
        source: str = "ai_inferred",
        confidence: float = 0.7,
    ) -> object:
        """Create or update a project memory entry.

        Args:
            repo: Memory repository instance.
            project_id: Project UUID.
            category: Memory category.
            key: Memory key.
            value: JSONB value.
            source: Source indicator.
            confidence: Confidence score.

        Returns:
            The upserted ProjectMemory row.
        """
        row = await repo.upsert(
            project_id=project_id,
            category=category,
            key=key,
            value=value,
            confidence=confidence,
            source=source,
        )
        await logger.ainfo(
            "project_memory_updated",
            project_id=str(project_id),
            category=category,
            key=key,
            source=source,
        )
        return row

    async def get_project_summary(
        self,
        repo: MemoryRepository,
        project_id: uuid.UUID,
    ) -> dict[str, object]:
        """Get a summary of all project memories.

        Args:
            repo: Memory repository instance.
            project_id: Project UUID.

        Returns:
            Summary dict grouped by category.
        """
        summary = await repo.get_project_summary(project_id)
        return dict(summary)

    # --- Layer 3: Personal Memory (mem0 + pgvector) ---

    async def save_conversation_facts(
        self,
        user_id: str,
        session_id: str,
        messages: list[dict[str, str]],
    ) -> list[str]:
        """Extract and save facts from a conversation to mem0.

        Called at session end. mem0 performs automatic fact extraction.

        Args:
            user_id: User identifier.
            session_id: Session identifier.
            messages: Conversation messages to extract facts from.

        Returns:
            List of extracted memory IDs.
        """
        mem0 = self._get_mem0()

        await logger.ainfo(
            "saving_conversation_facts",
            user_id=user_id,
            session_id=session_id,
            message_count=len(messages),
        )

        try:
            result = mem0.add(  # type: ignore[attr-defined]
                messages=messages,
                user_id=user_id,
                metadata={
                    "session_id": session_id,
                },
            )
            memory_ids: list[str] = []
            if isinstance(result, dict) and "results" in result:
                for item in result["results"]:
                    if isinstance(item, dict) and "id" in item:
                        memory_ids.append(str(item["id"]))

            await logger.ainfo(
                "conversation_facts_saved",
                user_id=user_id,
                session_id=session_id,
                facts_count=len(memory_ids),
            )
            return memory_ids
        except Exception as exc:
            await logger.aexception(
                "conversation_facts_save_error",
                user_id=user_id,
                session_id=session_id,
            )
            raise MemoryServiceError(
                f"Conversation fact extraction basarisiz: {exc}",
                operation="save_conversation_facts",
            ) from exc

    async def search_memories(
        self,
        user_id: str,
        query: str,
        limit: int = 10,
    ) -> list[PersonalMemoryItem]:
        """Search personal memories via semantic search.

        Args:
            user_id: User identifier.
            query: Search query text.
            limit: Maximum results.

        Returns:
            List of matching PersonalMemoryItem.
        """
        mem0 = self._get_mem0()

        try:
            results = mem0.search(  # type: ignore[attr-defined]
                query=query,
                user_id=user_id,
                limit=limit,
            )

            items: list[PersonalMemoryItem] = []
            if isinstance(results, dict) and "results" in results:
                search_results = results["results"]
            elif isinstance(results, list):
                search_results = results
            else:
                search_results = []

            for item in search_results:
                if not isinstance(item, dict):
                    continue
                score = item.get("score")
                if score is not None and float(score) < _SIMILARITY_THRESHOLD:
                    continue
                items.append(
                    PersonalMemoryItem(
                        id=str(item.get("id", "")),
                        memory=str(item.get("memory", "")),
                        score=float(score) if score is not None else None,
                        metadata=item.get("metadata"),
                    )
                )

            return items
        except MemoryServiceError:
            raise
        except Exception as exc:
            await logger.aexception(
                "personal_memory_search_error",
                user_id=user_id,
                query=query,
            )
            raise MemoryServiceError(
                f"Hafiza arama basarisiz: {exc}",
                operation="search_memories",
            ) from exc

    async def delete_personal_memory(self, memory_id: str) -> bool:
        """Delete a personal memory from mem0.

        Args:
            memory_id: mem0 memory ID.

        Returns:
            True if successful.
        """
        mem0 = self._get_mem0()
        try:
            mem0.delete(memory_id=memory_id)  # type: ignore[attr-defined]
            await logger.ainfo("personal_memory_deleted", memory_id=memory_id)
            return True
        except Exception as exc:
            await logger.aexception("personal_memory_delete_error", memory_id=memory_id)
            raise MemoryServiceError(
                f"Hafiza silme basarisiz: {exc}",
                operation="delete_personal_memory",
            ) from exc

    async def get_all_personal_memories(
        self,
        user_id: str,
    ) -> list[PersonalMemoryItem]:
        """Get all personal memories for a user.

        Args:
            user_id: User identifier.

        Returns:
            List of PersonalMemoryItem.
        """
        mem0 = self._get_mem0()
        try:
            results = mem0.get_all(user_id=user_id)  # type: ignore[attr-defined]
            items: list[PersonalMemoryItem] = []

            if isinstance(results, dict) and "results" in results:
                memory_list = results["results"]
            elif isinstance(results, list):
                memory_list = results
            else:
                memory_list = []

            for item in memory_list:
                if not isinstance(item, dict):
                    continue
                items.append(
                    PersonalMemoryItem(
                        id=str(item.get("id", "")),
                        memory=str(item.get("memory", "")),
                        score=None,
                        metadata=item.get("metadata"),
                    )
                )
            return items
        except Exception as exc:
            await logger.aexception("personal_memory_get_all_error", user_id=user_id)
            raise MemoryServiceError(
                f"Tum hafizalari getirme basarisiz: {exc}",
                operation="get_all_personal_memories",
            ) from exc

    # --- Context Building ---

    async def get_context_for_message(
        self,
        repo: MemoryRepository,
        user_id: str,
        message: str,
        project_id: uuid.UUID | None = None,
        session_id: str | None = None,
    ) -> MemoryContext:
        """Build full memory context for a Claude API call.

        Combines personal memories (mem0), project summary (PostgreSQL),
        and conversation summary into a single context object.

        Args:
            repo: Memory repository instance.
            user_id: User identifier.
            message: Current user message (for semantic search).
            project_id: Optional project UUID for project memory.
            session_id: Optional session ID for conversation summary.

        Returns:
            MemoryContext with all three layers.
        """
        # Personal memories via semantic search
        personal_memories: list[str] = []
        try:
            personal_items = await self.search_memories(
                user_id=user_id,
                query=message,
                limit=10,
            )
            personal_text = ""
            for item in personal_items:
                candidate = personal_text + item.memory + "\n"
                if self._estimate_tokens(candidate) > _PERSONAL_TOKEN_BUDGET:
                    break
                personal_text = candidate
                personal_memories.append(item.memory)
        except MemoryServiceError:
            await logger.awarning("personal_memory_unavailable", user_id=user_id)

        # Project summary
        project_summary: dict[str, object] = {}
        if project_id is not None:
            try:
                raw_summary = await repo.get_project_summary(project_id)
                summary_text = json.dumps(raw_summary, ensure_ascii=False)
                truncated = self._truncate_to_budget(summary_text, _PROJECT_TOKEN_BUDGET)
                project_summary = (
                    json.loads(truncated)
                    if truncated == summary_text
                    else {
                        "_truncated": True,
                        "_summary": truncated,
                    }
                )
            except Exception:
                await logger.awarning(
                    "project_memory_unavailable",
                    project_id=str(project_id),
                )

        # Conversation summary (from Redis cache, if previously stored)
        conversation_summary: str | None = None
        if session_id:
            cached = await redis_client.get_cache(f"conv_summary:{session_id}")
            if cached:
                conversation_summary = self._truncate_to_budget(
                    cached,
                    _CONVERSATION_SUMMARY_TOKEN_BUDGET,
                )

        # Calculate total token count
        total_text = (
            "\n".join(personal_memories)
            + json.dumps(project_summary, ensure_ascii=False)
            + (conversation_summary or "")
        )
        token_count = self._estimate_tokens(total_text)

        return MemoryContext(
            personal_memories=personal_memories,
            project_summary=project_summary,
            recent_actions=[],
            conversation_summary=conversation_summary,
            token_count=token_count,
        )


# Module-level singleton
memory_service = MemoryService()
