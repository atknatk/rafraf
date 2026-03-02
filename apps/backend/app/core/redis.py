"""Redis client wrapper for conversation memory and caching."""

import json

import redis.asyncio as aioredis
import structlog

from app.core.config import get_settings

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

# Conversation memory key prefix and default TTL (2 hours)
_CONVERSATION_PREFIX = "conv:"
_DEFAULT_TTL_SECONDS = 7200


class RedisClient:
    """Async Redis client for conversation memory storage.

    Conversation messages are stored per session with a TTL.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._url = settings.redis_url
        self._client: aioredis.Redis | None = None

    async def _get_client(self) -> aioredis.Redis:
        """Get or create the Redis connection.

        Returns:
            Connected Redis client.
        """
        if self._client is None:
            self._client = aioredis.from_url(
                self._url,
                decode_responses=True,
            )
        return self._client

    async def close(self) -> None:
        """Close the Redis connection."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # --- Conversation memory operations ---

    def _conv_key(self, session_id: str) -> str:
        """Build the Redis key for a conversation session.

        Args:
            session_id: Session identifier.

        Returns:
            Redis key string.
        """
        return f"{_CONVERSATION_PREFIX}{session_id}"

    async def save_conversation(
        self,
        session_id: str,
        messages: list[dict[str, str]],
        ttl: int = _DEFAULT_TTL_SECONDS,
    ) -> None:
        """Save conversation messages for a session.

        Args:
            session_id: Session identifier.
            messages: List of message dicts (role, content).
            ttl: Time-to-live in seconds.
        """
        client = await self._get_client()
        key = self._conv_key(session_id)
        await client.set(key, json.dumps(messages), ex=ttl)
        await logger.adebug("conversation_saved", session_id=session_id, count=len(messages))

    async def get_conversation(self, session_id: str) -> list[dict[str, str]]:
        """Retrieve conversation messages for a session.

        Args:
            session_id: Session identifier.

        Returns:
            List of message dicts, or empty list if not found.
        """
        client = await self._get_client()
        key = self._conv_key(session_id)
        raw = await client.get(key)
        if raw is None:
            return []
        messages: list[dict[str, str]] = json.loads(raw)
        return messages

    async def delete_conversation(self, session_id: str) -> bool:
        """Delete conversation cache for a session.

        Args:
            session_id: Session identifier.

        Returns:
            True if deleted, False if key did not exist.
        """
        client = await self._get_client()
        key = self._conv_key(session_id)
        deleted = await client.delete(key)
        return bool(deleted)

    async def append_message(
        self,
        session_id: str,
        message: dict[str, str],
        ttl: int = _DEFAULT_TTL_SECONDS,
    ) -> None:
        """Append a single message to the conversation history.

        Args:
            session_id: Session identifier.
            message: Message dict (role, content).
            ttl: Time-to-live in seconds (refreshed on each append).
        """
        messages = await self.get_conversation(session_id)
        messages.append(message)
        await self.save_conversation(session_id, messages, ttl=ttl)

    # --- Generic cache operations ---

    async def set_cache(self, key: str, value: str, ttl: int = 300) -> None:
        """Set a cache value with TTL.

        Args:
            key: Cache key.
            value: String value to cache.
            ttl: Time-to-live in seconds.
        """
        client = await self._get_client()
        await client.set(key, value, ex=ttl)

    async def get_cache(self, key: str) -> str | None:
        """Get a cached value.

        Args:
            key: Cache key.

        Returns:
            Cached string or None if not found.
        """
        client = await self._get_client()
        result = await client.get(key)
        if result is None:
            return None
        return str(result)


# Module-level singleton
redis_client = RedisClient()
