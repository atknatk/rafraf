"""Unit tests for RedisClient."""

import json
from unittest.mock import AsyncMock

from app.core.redis import RedisClient


class TestConversationOperations:
    """Tests for conversation memory Redis operations."""

    async def test_save_conversation(self) -> None:
        """save_conversation should store JSON in Redis with TTL."""
        client = RedisClient()
        messages = [{"role": "user", "content": "Hello"}]

        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock()
        client._client = mock_redis

        await client.save_conversation("sess_1", messages, ttl=3600)

        mock_redis.set.assert_called_once_with(
            "conv:sess_1",
            json.dumps(messages),
            ex=3600,
        )

    async def test_get_conversation_exists(self) -> None:
        """get_conversation should return parsed messages."""
        client = RedisClient()
        expected = [{"role": "user", "content": "Test"}]

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=json.dumps(expected))
        client._client = mock_redis

        result = await client.get_conversation("sess_1")
        assert result == expected

    async def test_get_conversation_not_found(self) -> None:
        """get_conversation should return empty list if key not found."""
        client = RedisClient()

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        client._client = mock_redis

        result = await client.get_conversation("sess_missing")
        assert result == []

    async def test_delete_conversation_exists(self) -> None:
        """delete_conversation should return True if key existed."""
        client = RedisClient()

        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock(return_value=1)
        client._client = mock_redis

        result = await client.delete_conversation("sess_1")
        assert result is True

    async def test_delete_conversation_not_found(self) -> None:
        """delete_conversation should return False if key did not exist."""
        client = RedisClient()

        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock(return_value=0)
        client._client = mock_redis

        result = await client.delete_conversation("sess_missing")
        assert result is False

    async def test_append_message(self) -> None:
        """append_message should add message and re-save."""
        client = RedisClient()
        existing = [{"role": "user", "content": "First"}]
        new_msg = {"role": "assistant", "content": "Reply"}

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=json.dumps(existing))
        mock_redis.set = AsyncMock()
        client._client = mock_redis

        await client.append_message("sess_1", new_msg, ttl=3600)

        # Should save both messages
        expected = existing + [new_msg]
        mock_redis.set.assert_called_once_with(
            "conv:sess_1",
            json.dumps(expected),
            ex=3600,
        )


class TestCacheOperations:
    """Tests for generic cache operations."""

    async def test_set_cache(self) -> None:
        """set_cache should store value with TTL."""
        client = RedisClient()

        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock()
        client._client = mock_redis

        await client.set_cache("key1", "value1", ttl=60)
        mock_redis.set.assert_called_once_with("key1", "value1", ex=60)

    async def test_get_cache_exists(self) -> None:
        """get_cache should return cached value."""
        client = RedisClient()

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value="cached_value")
        client._client = mock_redis

        result = await client.get_cache("key1")
        assert result == "cached_value"

    async def test_get_cache_not_found(self) -> None:
        """get_cache should return None if key not found."""
        client = RedisClient()

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        client._client = mock_redis

        result = await client.get_cache("missing_key")
        assert result is None

    async def test_close(self) -> None:
        """close should close the Redis connection."""
        client = RedisClient()

        mock_redis = AsyncMock()
        mock_redis.aclose = AsyncMock()
        client._client = mock_redis

        await client.close()
        mock_redis.aclose.assert_called_once()
        assert client._client is None


class TestConvKey:
    """Tests for _conv_key helper."""

    def test_conv_key_format(self) -> None:
        """_conv_key should prefix session_id with conv:."""
        client = RedisClient()
        assert client._conv_key("session_123") == "conv:session_123"
