"""Unit tests for ConversationMemoryService."""

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from app.services.conversation_memory_service import (
    ConversationMemoryService,
    SessionEndedError,
    SessionNotFoundError,
    _estimate_tokens,
)


class TestEstimateTokens:
    """Tests for _estimate_tokens helper."""

    def test_empty_string_returns_one(self) -> None:
        """Empty string should return minimum 1 token."""
        assert _estimate_tokens("") == 1

    def test_short_string(self) -> None:
        """Short string should return at least 1."""
        assert _estimate_tokens("Hi") == 1

    def test_standard_string(self) -> None:
        """Standard string should return chars / 4."""
        assert _estimate_tokens("12345678") == 2

    def test_long_string(self) -> None:
        """Long string should return proportional tokens."""
        text = "a" * 4000
        assert _estimate_tokens(text) == 1000


class TestCreateSession:
    """Tests for ConversationMemoryService.create_session."""

    async def test_create_session_success(self) -> None:
        """create_session should store metadata in Redis and return session."""
        svc = ConversationMemoryService()

        with (
            patch(
                "app.services.conversation_memory_service.redis_client"
            ) as mock_redis,
            patch(
                "app.services.conversation_memory_service.get_settings"
            ) as mock_settings,
        ):
            mock_settings.return_value.conversation_ttl_seconds = 86400
            mock_redis.hset_mapping = AsyncMock()
            mock_redis.sadd = AsyncMock()

            session = await svc.create_session(user_id="user1", project_id="proj1")

        assert session.user_id == "user1"
        assert session.project_id == "proj1"
        assert session.status == "active"
        assert session.message_count == 0
        assert session.total_tokens == 0
        assert session.session_id  # Non-empty UUID string
        mock_redis.hset_mapping.assert_called_once()
        mock_redis.sadd.assert_called_once()

    async def test_create_session_custom_ttl(self) -> None:
        """create_session should use custom TTL when provided."""
        svc = ConversationMemoryService()

        with (
            patch(
                "app.services.conversation_memory_service.redis_client"
            ) as mock_redis,
            patch(
                "app.services.conversation_memory_service.get_settings"
            ) as mock_settings,
        ):
            mock_settings.return_value.conversation_ttl_seconds = 86400
            mock_redis.hset_mapping = AsyncMock()
            mock_redis.sadd = AsyncMock()

            session = await svc.create_session(
                user_id="user1", ttl_seconds=3600
            )

        assert session.status == "active"
        # Verify custom TTL was passed
        call_args = mock_redis.hset_mapping.call_args
        assert call_args.kwargs.get("ttl") == 3600 or call_args[1].get("ttl") == 3600

    async def test_create_session_without_project(self) -> None:
        """create_session should work without project_id."""
        svc = ConversationMemoryService()

        with (
            patch(
                "app.services.conversation_memory_service.redis_client"
            ) as mock_redis,
            patch(
                "app.services.conversation_memory_service.get_settings"
            ) as mock_settings,
        ):
            mock_settings.return_value.conversation_ttl_seconds = 86400
            mock_redis.hset_mapping = AsyncMock()
            mock_redis.sadd = AsyncMock()

            session = await svc.create_session(user_id="user1")

        assert session.project_id is None


class TestGetSession:
    """Tests for ConversationMemoryService.get_session."""

    async def test_get_session_success(self) -> None:
        """get_session should return session from Redis."""
        svc = ConversationMemoryService()
        now = datetime.now(tz=UTC).isoformat()

        with patch(
            "app.services.conversation_memory_service.redis_client"
        ) as mock_redis:
            mock_redis.hgetall = AsyncMock(
                return_value={
                    "session_id": "sess-123",
                    "user_id": "user1",
                    "project_id": "",
                    "status": "active",
                    "message_count": "5",
                    "total_tokens": "100",
                    "created_at": now,
                    "last_activity_at": now,
                }
            )
            mock_redis.get_cache = AsyncMock(return_value=None)

            session = await svc.get_session("sess-123")

        assert session.session_id == "sess-123"
        assert session.user_id == "user1"
        assert session.project_id is None  # Empty string -> None
        assert session.status == "active"
        assert session.message_count == 5
        assert session.total_tokens == 100

    async def test_get_session_not_found_raises(self) -> None:
        """get_session should raise SessionNotFoundError for missing session."""
        svc = ConversationMemoryService()

        with patch(
            "app.services.conversation_memory_service.redis_client"
        ) as mock_redis:
            mock_redis.hgetall = AsyncMock(return_value={})

            with pytest.raises(SessionNotFoundError, match="bulunamadi"):
                await svc.get_session("nonexistent")

    async def test_get_session_with_summary(self) -> None:
        """get_session should include summary if available."""
        svc = ConversationMemoryService()
        now = datetime.now(tz=UTC).isoformat()

        with patch(
            "app.services.conversation_memory_service.redis_client"
        ) as mock_redis:
            mock_redis.hgetall = AsyncMock(
                return_value={
                    "session_id": "sess-123",
                    "user_id": "user1",
                    "project_id": "",
                    "status": "summarized",
                    "message_count": "10",
                    "total_tokens": "500",
                    "created_at": now,
                    "last_activity_at": now,
                }
            )
            mock_redis.get_cache = AsyncMock(
                return_value="This is a session summary."
            )

            session = await svc.get_session("sess-123")

        assert session.summary == "This is a session summary."
        assert session.status == "summarized"


class TestAddMessage:
    """Tests for ConversationMemoryService.add_message."""

    async def test_add_message_success(self) -> None:
        """add_message should append to Redis and update metadata."""
        svc = ConversationMemoryService()
        now = datetime.now(tz=UTC).isoformat()

        with (
            patch(
                "app.services.conversation_memory_service.redis_client"
            ) as mock_redis,
            patch(
                "app.services.conversation_memory_service.get_settings"
            ) as mock_settings,
        ):
            mock_settings.return_value.conversation_ttl_seconds = 86400
            # Mock get_session
            mock_redis.hgetall = AsyncMock(
                return_value={
                    "session_id": "sess-123",
                    "user_id": "user1",
                    "project_id": "",
                    "status": "active",
                    "message_count": "2",
                    "total_tokens": "50",
                    "created_at": now,
                    "last_activity_at": now,
                }
            )
            mock_redis.get_cache = AsyncMock(return_value=None)
            mock_redis.rpush = AsyncMock(return_value=3)
            mock_redis.hset_mapping = AsyncMock()
            mock_redis.expire = AsyncMock()

            message = await svc.add_message(
                session_id="sess-123",
                role="user",
                content="Hello, world!",
            )

        assert message.role == "user"
        assert message.content == "Hello, world!"
        assert message.token_count == _estimate_tokens("Hello, world!")
        assert message.id  # Non-empty
        mock_redis.rpush.assert_called_once()
        mock_redis.hset_mapping.assert_called_once()

    async def test_add_message_ended_session_raises(self) -> None:
        """add_message should raise SessionEndedError for ended sessions."""
        svc = ConversationMemoryService()
        now = datetime.now(tz=UTC).isoformat()

        with patch(
            "app.services.conversation_memory_service.redis_client"
        ) as mock_redis:
            mock_redis.hgetall = AsyncMock(
                return_value={
                    "session_id": "sess-123",
                    "user_id": "user1",
                    "project_id": "",
                    "status": "ended",
                    "message_count": "5",
                    "total_tokens": "100",
                    "created_at": now,
                    "last_activity_at": now,
                }
            )
            mock_redis.get_cache = AsyncMock(return_value=None)

            with pytest.raises(SessionEndedError, match="sonlandirilmis"):
                await svc.add_message(
                    session_id="sess-123",
                    role="user",
                    content="Should fail",
                )

    async def test_add_message_with_metadata(self) -> None:
        """add_message should store metadata correctly."""
        svc = ConversationMemoryService()
        now = datetime.now(tz=UTC).isoformat()

        with (
            patch(
                "app.services.conversation_memory_service.redis_client"
            ) as mock_redis,
            patch(
                "app.services.conversation_memory_service.get_settings"
            ) as mock_settings,
        ):
            mock_settings.return_value.conversation_ttl_seconds = 86400
            mock_redis.hgetall = AsyncMock(
                return_value={
                    "session_id": "sess-123",
                    "user_id": "user1",
                    "project_id": "",
                    "status": "active",
                    "message_count": "0",
                    "total_tokens": "0",
                    "created_at": now,
                    "last_activity_at": now,
                }
            )
            mock_redis.get_cache = AsyncMock(return_value=None)
            mock_redis.rpush = AsyncMock(return_value=1)
            mock_redis.hset_mapping = AsyncMock()
            mock_redis.expire = AsyncMock()

            message = await svc.add_message(
                session_id="sess-123",
                role="assistant",
                content="Response",
                metadata={"model_used": "claude-sonnet"},
            )

        assert message.metadata == {"model_used": "claude-sonnet"}


class TestGetMessages:
    """Tests for ConversationMemoryService.get_messages."""

    async def test_get_messages_success(self) -> None:
        """get_messages should return paginated message list."""
        svc = ConversationMemoryService()
        now = datetime.now(tz=UTC)
        now_iso = now.isoformat()

        msg_data = {
            "id": "msg-1",
            "role": "user",
            "content": "Hello",
            "timestamp": now_iso,
            "token_count": 2,
            "metadata": None,
        }

        with patch(
            "app.services.conversation_memory_service.redis_client"
        ) as mock_redis:
            mock_redis.hgetall = AsyncMock(
                return_value={
                    "session_id": "sess-123",
                    "user_id": "user1",
                    "project_id": "",
                    "status": "active",
                    "message_count": "3",
                    "total_tokens": "30",
                    "created_at": now_iso,
                    "last_activity_at": now_iso,
                }
            )
            mock_redis.get_cache = AsyncMock(return_value=None)
            mock_redis.llen = AsyncMock(return_value=3)
            mock_redis.lrange = AsyncMock(
                return_value=[json.dumps(msg_data)]
            )

            messages, total, has_more = await svc.get_messages(
                "sess-123", limit=2, offset=0
            )

        assert len(messages) == 1
        assert total == 3
        assert messages[0].role == "user"

    async def test_get_messages_has_more(self) -> None:
        """get_messages should indicate when more messages are available."""
        svc = ConversationMemoryService()
        now_iso = datetime.now(tz=UTC).isoformat()

        with patch(
            "app.services.conversation_memory_service.redis_client"
        ) as mock_redis:
            mock_redis.hgetall = AsyncMock(
                return_value={
                    "session_id": "sess-123",
                    "user_id": "user1",
                    "project_id": "",
                    "status": "active",
                    "message_count": "10",
                    "total_tokens": "100",
                    "created_at": now_iso,
                    "last_activity_at": now_iso,
                }
            )
            mock_redis.get_cache = AsyncMock(return_value=None)
            mock_redis.llen = AsyncMock(return_value=10)
            mock_redis.lrange = AsyncMock(return_value=[])

            _, total, has_more = await svc.get_messages(
                "sess-123", limit=5, offset=0
            )

        assert total == 10
        assert has_more is True

    async def test_get_messages_no_more(self) -> None:
        """get_messages should return has_more=False when at end."""
        svc = ConversationMemoryService()
        now_iso = datetime.now(tz=UTC).isoformat()

        with patch(
            "app.services.conversation_memory_service.redis_client"
        ) as mock_redis:
            mock_redis.hgetall = AsyncMock(
                return_value={
                    "session_id": "sess-123",
                    "user_id": "user1",
                    "project_id": "",
                    "status": "active",
                    "message_count": "3",
                    "total_tokens": "30",
                    "created_at": now_iso,
                    "last_activity_at": now_iso,
                }
            )
            mock_redis.get_cache = AsyncMock(return_value=None)
            mock_redis.llen = AsyncMock(return_value=3)
            mock_redis.lrange = AsyncMock(return_value=[])

            _, total, has_more = await svc.get_messages(
                "sess-123", limit=50, offset=0
            )

        assert total == 3
        assert has_more is False


class TestGetContextWindow:
    """Tests for ConversationMemoryService.get_context_window."""

    async def test_context_window_all_fit(self) -> None:
        """get_context_window should include all messages when budget allows."""
        svc = ConversationMemoryService()
        now_iso = datetime.now(tz=UTC).isoformat()

        msgs = [
            json.dumps({
                "id": f"msg-{i}",
                "role": "user",
                "content": "Short msg",
                "timestamp": now_iso,
                "token_count": 3,
                "metadata": None,
            })
            for i in range(3)
        ]

        with (
            patch(
                "app.services.conversation_memory_service.redis_client"
            ) as mock_redis,
            patch(
                "app.services.conversation_memory_service.get_settings"
            ) as mock_settings,
        ):
            mock_settings.return_value.conversation_max_tokens = 50000
            mock_redis.hgetall = AsyncMock(
                return_value={
                    "session_id": "sess-123",
                    "user_id": "user1",
                    "project_id": "",
                    "status": "active",
                    "message_count": "3",
                    "total_tokens": "9",
                    "created_at": now_iso,
                    "last_activity_at": now_iso,
                }
            )
            mock_redis.get_cache = AsyncMock(return_value=None)
            mock_redis.lrange = AsyncMock(return_value=msgs)

            result = await svc.get_context_window("sess-123")

        assert result.messages_included == 3
        assert result.messages_summarized == 0

    async def test_context_window_budget_exceeded(self) -> None:
        """get_context_window should exclude oldest messages when over budget."""
        svc = ConversationMemoryService()
        now_iso = datetime.now(tz=UTC).isoformat()

        # Create messages with large token counts
        msgs = [
            json.dumps({
                "id": f"msg-{i}",
                "role": "user",
                "content": "x" * 400,  # ~100 tokens each
                "timestamp": now_iso,
                "token_count": 100,
                "metadata": None,
            })
            for i in range(10)
        ]

        with (
            patch(
                "app.services.conversation_memory_service.redis_client"
            ) as mock_redis,
            patch(
                "app.services.conversation_memory_service.get_settings"
            ) as mock_settings,
        ):
            mock_settings.return_value.conversation_max_tokens = 50000
            mock_redis.hgetall = AsyncMock(
                return_value={
                    "session_id": "sess-123",
                    "user_id": "user1",
                    "project_id": "",
                    "status": "active",
                    "message_count": "10",
                    "total_tokens": "1000",
                    "created_at": now_iso,
                    "last_activity_at": now_iso,
                }
            )
            mock_redis.get_cache = AsyncMock(return_value=None)
            mock_redis.lrange = AsyncMock(return_value=msgs)

            # Set a small budget so only a few messages fit
            result = await svc.get_context_window("sess-123", max_tokens=350)

        assert result.messages_included < 10
        assert result.messages_summarized > 0
        assert result.total_tokens <= 350


class TestSummarizeSession:
    """Tests for ConversationMemoryService.summarize_session."""

    async def test_summarize_auto_generated(self) -> None:
        """summarize_session should generate truncation-based summary."""
        svc = ConversationMemoryService()
        now_iso = datetime.now(tz=UTC).isoformat()

        msgs = [
            json.dumps({
                "id": "msg-1",
                "role": "user",
                "content": "Hello, how are you?",
                "timestamp": now_iso,
                "token_count": 5,
                "metadata": None,
            }),
            json.dumps({
                "id": "msg-2",
                "role": "assistant",
                "content": "I am fine, thank you!",
                "timestamp": now_iso,
                "token_count": 6,
                "metadata": None,
            }),
        ]

        with (
            patch(
                "app.services.conversation_memory_service.redis_client"
            ) as mock_redis,
            patch(
                "app.services.conversation_memory_service.get_settings"
            ) as mock_settings,
        ):
            mock_settings.return_value.conversation_ttl_seconds = 86400
            mock_redis.hgetall = AsyncMock(
                return_value={
                    "session_id": "sess-123",
                    "user_id": "user1",
                    "project_id": "",
                    "status": "active",
                    "message_count": "2",
                    "total_tokens": "11",
                    "created_at": now_iso,
                    "last_activity_at": now_iso,
                }
            )
            mock_redis.get_cache = AsyncMock(return_value=None)
            mock_redis.lrange = AsyncMock(return_value=msgs)
            mock_redis.set_cache = AsyncMock()
            mock_redis.hset_field = AsyncMock()

            result = await svc.summarize_session("sess-123")

        assert result.session_id == "sess-123"
        assert "user:" in result.summary
        assert "assistant:" in result.summary
        assert result.original_message_count == 2
        assert result.original_token_count == 11
        assert result.summary_token_count > 0
        mock_redis.set_cache.assert_called_once()
        mock_redis.hset_field.assert_called_once()

    async def test_summarize_with_custom_text(self) -> None:
        """summarize_session should use custom summary_text when provided."""
        svc = ConversationMemoryService()
        now_iso = datetime.now(tz=UTC).isoformat()

        with (
            patch(
                "app.services.conversation_memory_service.redis_client"
            ) as mock_redis,
            patch(
                "app.services.conversation_memory_service.get_settings"
            ) as mock_settings,
        ):
            mock_settings.return_value.conversation_ttl_seconds = 86400
            mock_redis.hgetall = AsyncMock(
                return_value={
                    "session_id": "sess-123",
                    "user_id": "user1",
                    "project_id": "",
                    "status": "active",
                    "message_count": "5",
                    "total_tokens": "100",
                    "created_at": now_iso,
                    "last_activity_at": now_iso,
                }
            )
            mock_redis.get_cache = AsyncMock(return_value=None)
            mock_redis.lrange = AsyncMock(return_value=[])
            mock_redis.set_cache = AsyncMock()
            mock_redis.hset_field = AsyncMock()

            result = await svc.summarize_session(
                "sess-123", summary_text="AI-generated summary"
            )

        assert result.summary == "AI-generated summary"


class TestEndSession:
    """Tests for ConversationMemoryService.end_session."""

    async def test_end_active_session(self) -> None:
        """end_session should create summary and clean up."""
        svc = ConversationMemoryService()
        now_iso = datetime.now(tz=UTC).isoformat()

        with (
            patch(
                "app.services.conversation_memory_service.redis_client"
            ) as mock_redis,
            patch(
                "app.services.conversation_memory_service.get_settings"
            ) as mock_settings,
        ):
            mock_settings.return_value.conversation_ttl_seconds = 86400
            mock_redis.hgetall = AsyncMock(
                return_value={
                    "session_id": "sess-123",
                    "user_id": "user1",
                    "project_id": "",
                    "status": "active",
                    "message_count": "3",
                    "total_tokens": "50",
                    "created_at": now_iso,
                    "last_activity_at": now_iso,
                }
            )
            mock_redis.get_cache = AsyncMock(return_value=None)
            mock_redis.lrange = AsyncMock(return_value=[])
            mock_redis.set_cache = AsyncMock()
            mock_redis.hset_field = AsyncMock()
            mock_redis.delete_key = AsyncMock(return_value=True)
            mock_redis.srem = AsyncMock()

            await svc.end_session("sess-123")

        # Verify cleanup operations
        mock_redis.hset_field.assert_called()
        mock_redis.delete_key.assert_called_once()
        mock_redis.srem.assert_called_once()

    async def test_end_nonexistent_session_raises(self) -> None:
        """end_session should raise SessionNotFoundError for missing session."""
        svc = ConversationMemoryService()

        with patch(
            "app.services.conversation_memory_service.redis_client"
        ) as mock_redis:
            mock_redis.hgetall = AsyncMock(return_value={})

            with pytest.raises(SessionNotFoundError):
                await svc.end_session("nonexistent")


class TestGetUserSessions:
    """Tests for ConversationMemoryService.get_user_sessions."""

    async def test_get_user_sessions(self) -> None:
        """get_user_sessions should return session IDs from Redis set."""
        svc = ConversationMemoryService()

        with patch(
            "app.services.conversation_memory_service.redis_client"
        ) as mock_redis:
            mock_redis.smembers = AsyncMock(
                return_value={"sess-1", "sess-2", "sess-3"}
            )

            sessions = await svc.get_user_sessions("user1")

        assert len(sessions) == 3
        assert set(sessions) == {"sess-1", "sess-2", "sess-3"}

    async def test_get_user_sessions_empty(self) -> None:
        """get_user_sessions should return empty list for no sessions."""
        svc = ConversationMemoryService()

        with patch(
            "app.services.conversation_memory_service.redis_client"
        ) as mock_redis:
            mock_redis.smembers = AsyncMock(return_value=set())

            sessions = await svc.get_user_sessions("user1")

        assert sessions == []
