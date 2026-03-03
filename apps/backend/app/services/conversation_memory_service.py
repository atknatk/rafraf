"""Conversation memory service - Redis-based session management.

Manages conversation sessions with:
- Session lifecycle (create, get, end)
- Message storage (append, retrieve with pagination)
- TTL-based auto-cleanup
- Context window management (token limiting)
- Session summarization
"""

import json
import uuid
from datetime import UTC, datetime

import structlog

from app.core.config import get_settings
from app.core.redis import redis_client
from app.schemas.conversation_memory import (
    ConversationContextResponse,
    ConversationMessage,
    ConversationSession,
    ConversationSummaryResponse,
)

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

# Redis key prefixes
_SESSION_META_PREFIX = "conv:session:"
_SESSION_META_SUFFIX = ":meta"
_SESSION_MSGS_SUFFIX = ":messages"
_SESSION_SUMMARY_SUFFIX = ":summary"
_USER_SESSIONS_PREFIX = "conv:user:"
_USER_SESSIONS_SUFFIX = ":sessions"

# Token estimation: 1 token ~ 4 characters
_CHARS_PER_TOKEN = 4


class ConversationMemoryError(Exception):
    """Raised when a conversation memory operation fails."""

    def __init__(self, message: str, operation: str = "") -> None:
        self.operation = operation
        super().__init__(message)


class SessionNotFoundError(ConversationMemoryError):
    """Raised when a session is not found in Redis."""

    def __init__(self, session_id: str) -> None:
        super().__init__(
            f"Session '{session_id}' bulunamadi",
            operation="get_session",
        )


class SessionEndedError(ConversationMemoryError):
    """Raised when trying to modify an ended session."""

    def __init__(self, session_id: str) -> None:
        super().__init__(
            f"Session '{session_id}' sonlandirilmis, mesaj eklenemez",
            operation="add_message",
        )


def _estimate_tokens(text: str) -> int:
    """Estimate token count from character length.

    Args:
        text: Input text.

    Returns:
        Estimated token count.
    """
    return max(1, len(text) // _CHARS_PER_TOKEN)


def _meta_key(session_id: str) -> str:
    return f"{_SESSION_META_PREFIX}{session_id}{_SESSION_META_SUFFIX}"


def _msgs_key(session_id: str) -> str:
    return f"{_SESSION_META_PREFIX}{session_id}{_SESSION_MSGS_SUFFIX}"


def _summary_key(session_id: str) -> str:
    return f"{_SESSION_META_PREFIX}{session_id}{_SESSION_SUMMARY_SUFFIX}"


def _user_sessions_key(user_id: str) -> str:
    return f"{_USER_SESSIONS_PREFIX}{user_id}{_USER_SESSIONS_SUFFIX}"


class ConversationMemoryService:
    """Redis-based conversation memory management.

    Handles full session lifecycle with message storage,
    TTL management, and context window optimization.
    """

    async def create_session(
        self,
        user_id: str,
        project_id: str | None = None,
        ttl_seconds: int | None = None,
    ) -> ConversationSession:
        """Create a new conversation session.

        Args:
            user_id: User identifier.
            project_id: Optional project identifier.
            ttl_seconds: Optional TTL override (seconds).

        Returns:
            Created ConversationSession.
        """
        settings = get_settings()
        ttl = ttl_seconds if ttl_seconds is not None else settings.conversation_ttl_seconds
        session_id = str(uuid.uuid4())
        now = datetime.now(tz=UTC)

        meta: dict[str, str] = {
            "session_id": session_id,
            "user_id": user_id,
            "project_id": project_id or "",
            "status": "active",
            "message_count": "0",
            "total_tokens": "0",
            "created_at": now.isoformat(),
            "last_activity_at": now.isoformat(),
        }

        key = _meta_key(session_id)

        # Store session metadata as a hash
        await redis_client.hset_mapping(key, meta, ttl=ttl)

        # Track user's active sessions
        user_key = _user_sessions_key(user_id)
        await redis_client.sadd(user_key, session_id, ttl=ttl)

        await logger.ainfo(
            "conversation_session_created",
            session_id=session_id,
            user_id=user_id,
            ttl_seconds=ttl,
        )

        return ConversationSession(
            session_id=session_id,
            user_id=user_id,
            project_id=project_id,
            status="active",
            message_count=0,
            total_tokens=0,
            created_at=now,
            last_activity_at=now,
            summary=None,
        )

    async def get_session(self, session_id: str) -> ConversationSession:
        """Retrieve session metadata.

        Args:
            session_id: Session identifier.

        Returns:
            ConversationSession.

        Raises:
            SessionNotFoundError: If session does not exist.
        """
        key = _meta_key(session_id)
        meta = await redis_client.hgetall(key)

        if not meta:
            raise SessionNotFoundError(session_id)

        # Get summary if exists
        s_key = _summary_key(session_id)
        summary = await redis_client.get_cache(s_key)

        return ConversationSession(
            session_id=meta["session_id"],
            user_id=meta["user_id"],
            project_id=meta["project_id"] or None,
            status=meta["status"],
            message_count=int(meta["message_count"]),
            total_tokens=int(meta["total_tokens"]),
            created_at=datetime.fromisoformat(meta["created_at"]),
            last_activity_at=datetime.fromisoformat(meta["last_activity_at"])
            if meta.get("last_activity_at")
            else None,
            summary=summary,
        )

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: dict[str, str] | None = None,
    ) -> ConversationMessage:
        """Add a message to a conversation session.

        Appends the message to the Redis list, updates session metadata,
        and refreshes TTL.

        Args:
            session_id: Session identifier.
            role: Message role (user, assistant, tool, system).
            content: Message content.
            metadata: Optional message metadata.

        Returns:
            Created ConversationMessage.

        Raises:
            SessionNotFoundError: If session does not exist.
            SessionEndedError: If session has been ended.
        """
        session = await self.get_session(session_id)

        if session.status != "active":
            raise SessionEndedError(session_id)

        settings = get_settings()
        ttl = settings.conversation_ttl_seconds

        msg_id = str(uuid.uuid4())
        now = datetime.now(tz=UTC)
        token_count = _estimate_tokens(content)

        message = ConversationMessage(
            id=msg_id,
            role=role,
            content=content,
            timestamp=now,
            token_count=token_count,
            metadata=metadata,
        )

        # Append message to list
        msgs_key = _msgs_key(session_id)
        msg_json = json.dumps(message.model_dump(mode="json"))
        await redis_client.rpush(msgs_key, msg_json, ttl=ttl)

        # Update session metadata
        meta_key = _meta_key(session_id)
        new_count = session.message_count + 1
        new_tokens = session.total_tokens + token_count
        await redis_client.hset_mapping(
            meta_key,
            {
                "message_count": str(new_count),
                "total_tokens": str(new_tokens),
                "last_activity_at": now.isoformat(),
            },
        )
        await redis_client.expire(meta_key, ttl)

        await logger.ainfo(
            "conversation_message_added",
            session_id=session_id,
            role=role,
            token_count=token_count,
            total_tokens=new_tokens,
        )

        return message

    async def get_messages(
        self,
        session_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[ConversationMessage], int, bool]:
        """Retrieve messages for a session with pagination.

        Args:
            session_id: Session identifier.
            limit: Maximum number of messages to return.
            offset: Starting position.

        Returns:
            Tuple of (messages, total_count, has_more).

        Raises:
            SessionNotFoundError: If session does not exist.
        """
        # Verify session exists
        await self.get_session(session_id)

        msgs_key = _msgs_key(session_id)

        total = await redis_client.llen(msgs_key)
        end = offset + limit - 1
        raw_messages = await redis_client.lrange(msgs_key, offset, end)

        messages: list[ConversationMessage] = []
        for raw in raw_messages:
            data = json.loads(raw)
            messages.append(ConversationMessage(**data))

        has_more = (offset + limit) < total

        return messages, total, has_more

    async def get_context_window(
        self,
        session_id: str,
        max_tokens: int | None = None,
    ) -> ConversationContextResponse:
        """Get context-window-optimized message history.

        Returns the most recent messages that fit within the token budget.
        If there are older messages that don't fit, they are counted as
        summarized. If a session summary exists, it is included.

        Args:
            session_id: Session identifier.
            max_tokens: Maximum token limit. Defaults to config value.

        Returns:
            ConversationContextResponse with optimized messages.

        Raises:
            SessionNotFoundError: If session does not exist.
        """
        settings = get_settings()
        budget = max_tokens if max_tokens is not None else settings.conversation_max_tokens

        session = await self.get_session(session_id)

        msgs_key = _msgs_key(session_id)

        # Get all messages from Redis
        raw_all = await redis_client.lrange(msgs_key, 0, -1)

        all_messages: list[ConversationMessage] = []
        for raw in raw_all:
            data = json.loads(raw)
            all_messages.append(ConversationMessage(**data))

        # Include summary token cost if available
        summary = session.summary
        summary_tokens = _estimate_tokens(summary) if summary else 0
        remaining_budget = budget - summary_tokens

        # Walk backwards from most recent, include messages that fit
        included: list[dict[str, str]] = []
        included_tokens = 0
        cutoff_index = len(all_messages)

        for i in range(len(all_messages) - 1, -1, -1):
            msg = all_messages[i]
            if included_tokens + msg.token_count > remaining_budget:
                cutoff_index = i + 1
                break
            included_tokens += msg.token_count
            included.insert(0, {"role": msg.role, "content": msg.content})
            cutoff_index = i

        messages_summarized = cutoff_index
        total_tokens = included_tokens + summary_tokens

        return ConversationContextResponse(
            messages=included,
            summary=summary,
            total_tokens=total_tokens,
            messages_included=len(included),
            messages_summarized=messages_summarized,
        )

    async def summarize_session(
        self,
        session_id: str,
        summary_text: str | None = None,
    ) -> ConversationSummaryResponse:
        """Create a session summary.

        If summary_text is provided, it is used directly. Otherwise, a
        simple truncation-based summary is generated from the messages.
        (Full AI summarization is handled by the orchestrator layer.)

        Args:
            session_id: Session identifier.
            summary_text: Optional pre-generated summary text.

        Returns:
            ConversationSummaryResponse.

        Raises:
            SessionNotFoundError: If session does not exist.
        """
        session = await self.get_session(session_id)

        msgs_key = _msgs_key(session_id)

        # Get all messages
        raw_all = await redis_client.lrange(msgs_key, 0, -1)
        original_count = len(raw_all)
        original_tokens = session.total_tokens

        if summary_text is None:
            # Simple truncation-based summary from messages
            parts: list[str] = []
            for raw in raw_all:
                data = json.loads(raw)
                role = data.get("role", "unknown")
                content = data.get("content", "")
                # Truncate long messages
                if len(content) > 200:
                    content = content[:200] + "..."
                parts.append(f"{role}: {content}")
            full_text = "\n".join(parts)
            # Truncate to ~500 tokens (2000 chars)
            if len(full_text) > 2000:
                summary_text = full_text[:2000] + "\n[...truncated]"
            else:
                summary_text = full_text

        summary_token_count = _estimate_tokens(summary_text)

        # Store summary in Redis
        s_key = _summary_key(session_id)
        settings = get_settings()
        ttl = settings.conversation_ttl_seconds
        await redis_client.set_cache(s_key, summary_text, ttl=ttl)

        # Update session status
        meta_key = _meta_key(session_id)
        await redis_client.hset_field(meta_key, "status", "summarized")

        await logger.ainfo(
            "conversation_session_summarized",
            session_id=session_id,
            original_count=original_count,
            summary_tokens=summary_token_count,
        )

        return ConversationSummaryResponse(
            session_id=session_id,
            summary=summary_text,
            original_message_count=original_count,
            original_token_count=original_tokens,
            summary_token_count=summary_token_count,
        )

    async def end_session(
        self,
        session_id: str,
    ) -> None:
        """End a conversation session.

        Creates a summary, updates status, and cleans up message data
        (keeping only metadata and summary).

        Args:
            session_id: Session identifier.

        Raises:
            SessionNotFoundError: If session does not exist.
        """
        session = await self.get_session(session_id)

        # Generate summary before cleanup
        if session.status == "active":
            await self.summarize_session(session_id)

        # Update status to ended
        meta_key = _meta_key(session_id)
        await redis_client.hset_field(meta_key, "status", "ended")

        # Delete the messages list (keep meta + summary)
        msgs_key = _msgs_key(session_id)
        await redis_client.delete_key(msgs_key)

        # Remove from user's active sessions
        user_id = session.user_id
        user_key = _user_sessions_key(user_id)
        await redis_client.srem(user_key, session_id)

        await logger.ainfo(
            "conversation_session_ended",
            session_id=session_id,
            user_id=user_id,
            message_count=session.message_count,
        )

    async def get_user_sessions(self, user_id: str) -> list[str]:
        """Get all active session IDs for a user.

        Args:
            user_id: User identifier.

        Returns:
            List of session IDs.
        """
        user_key = _user_sessions_key(user_id)
        session_ids = await redis_client.smembers(user_key)
        return list(session_ids)


# Module-level singleton
conversation_memory_service = ConversationMemoryService()
