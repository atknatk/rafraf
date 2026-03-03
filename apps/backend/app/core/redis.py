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

    # --- Session-based conversation memory (hash + list) ---

    async def hset_mapping(self, key: str, mapping: dict[str, str], ttl: int = 0) -> None:
        """Set multiple hash fields from a mapping.

        Args:
            key: Redis key.
            mapping: Field-value mapping.
            ttl: Optional TTL in seconds (0 = no expiry).
        """
        client = await self._get_client()
        await client.hset(key, mapping=mapping)  # type: ignore[misc]
        if ttl > 0:
            await client.expire(key, ttl)

    async def hset_field(self, key: str, field: str, value: str) -> None:
        """Set a single hash field.

        Args:
            key: Redis key.
            field: Hash field name.
            value: Field value.
        """
        client = await self._get_client()
        await client.hset(key, field, value)  # type: ignore[misc]

    async def hgetall(self, key: str) -> dict[str, str]:
        """Get all hash fields.

        Args:
            key: Redis key.

        Returns:
            Dict of field-value pairs (empty if key doesn't exist).
        """
        client = await self._get_client()
        result: dict[str, str] = await client.hgetall(key)  # type: ignore[misc]
        return result

    async def rpush(self, key: str, value: str, ttl: int = 0) -> int:
        """Append a value to a list (right push).

        Args:
            key: Redis key.
            value: Value to push.
            ttl: Optional TTL in seconds (0 = no expiry).

        Returns:
            Length of the list after push.
        """
        client = await self._get_client()
        length: int = await client.rpush(key, value)  # type: ignore[misc]
        if ttl > 0:
            await client.expire(key, ttl)
        return length

    async def llen(self, key: str) -> int:
        """Get the length of a list.

        Args:
            key: Redis key.

        Returns:
            Length of the list.
        """
        client = await self._get_client()
        result: int = await client.llen(key)  # type: ignore[misc]
        return result

    async def lrange(self, key: str, start: int, stop: int) -> list[str]:
        """Get a range of elements from a list.

        Args:
            key: Redis key.
            start: Start index.
            stop: Stop index (-1 for all).

        Returns:
            List of string values.
        """
        client = await self._get_client()
        result: list[str] = await client.lrange(key, start, stop)  # type: ignore[misc]
        return result

    async def sadd(self, key: str, member: str, ttl: int = 0) -> None:
        """Add a member to a set.

        Args:
            key: Redis key.
            member: Set member.
            ttl: Optional TTL in seconds (0 = no expiry).
        """
        client = await self._get_client()
        await client.sadd(key, member)  # type: ignore[misc]
        if ttl > 0:
            await client.expire(key, ttl)

    async def srem(self, key: str, member: str) -> None:
        """Remove a member from a set.

        Args:
            key: Redis key.
            member: Set member.
        """
        client = await self._get_client()
        await client.srem(key, member)  # type: ignore[misc]

    async def smembers(self, key: str) -> set[str]:
        """Get all members of a set.

        Args:
            key: Redis key.

        Returns:
            Set of string members.
        """
        client = await self._get_client()
        result: set[str] = await client.smembers(key)  # type: ignore[misc]
        return result

    async def expire(self, key: str, ttl: int) -> None:
        """Set a TTL on a key.

        Args:
            key: Redis key.
            ttl: Time-to-live in seconds.
        """
        client = await self._get_client()
        await client.expire(key, ttl)

    async def delete_key(self, key: str) -> bool:
        """Delete a key.

        Args:
            key: Redis key.

        Returns:
            True if deleted, False if not found.
        """
        client = await self._get_client()
        deleted = await client.delete(key)
        return bool(deleted)

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
