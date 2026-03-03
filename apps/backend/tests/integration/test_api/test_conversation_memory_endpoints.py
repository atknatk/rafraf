"""Integration tests for conversation memory REST endpoints."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client() -> AsyncClient:
    """Create an async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestCreateSessionEndpoint:
    """Tests for POST /api/v1/conversations."""

    async def test_create_session_success(self, client: AsyncClient) -> None:
        """Should create a session and return 201."""
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

            response = await client.post(
                "/api/v1/conversations",
                json={"user_id": "testuser", "project_id": "proj-1"},
            )

        assert response.status_code == 201
        data = response.json()
        assert data["user_id"] == "testuser"
        assert data["project_id"] == "proj-1"
        assert data["status"] == "active"
        assert data["message_count"] == 0
        assert "session_id" in data

    async def test_create_session_missing_user_id(
        self, client: AsyncClient
    ) -> None:
        """Should return 422 for missing user_id."""
        response = await client.post(
            "/api/v1/conversations",
            json={},
        )
        assert response.status_code == 422


class TestGetSessionEndpoint:
    """Tests for GET /api/v1/conversations/{session_id}."""

    async def test_get_session_not_found(self, client: AsyncClient) -> None:
        """Should return 404 for nonexistent session."""
        with patch(
            "app.services.conversation_memory_service.redis_client"
        ) as mock_redis:
            mock_redis.hgetall = AsyncMock(return_value={})

            response = await client.get(
                "/api/v1/conversations/nonexistent-id"
            )

        assert response.status_code == 404


class TestAddMessageEndpoint:
    """Tests for POST /api/v1/conversations/{session_id}/messages."""

    async def test_add_message_to_nonexistent_session(
        self, client: AsyncClient
    ) -> None:
        """Should return 404 for nonexistent session."""
        with patch(
            "app.services.conversation_memory_service.redis_client"
        ) as mock_redis:
            mock_redis.hgetall = AsyncMock(return_value={})

            response = await client.post(
                "/api/v1/conversations/nonexistent/messages",
                json={"role": "user", "content": "Hello"},
            )

        assert response.status_code == 404

    async def test_add_message_invalid_role(
        self, client: AsyncClient
    ) -> None:
        """Should return 422 for invalid role."""
        response = await client.post(
            "/api/v1/conversations/sess-123/messages",
            json={"role": "invalid_role", "content": "Hello"},
        )
        assert response.status_code == 422


class TestEndSessionEndpoint:
    """Tests for DELETE /api/v1/conversations/{session_id}."""

    async def test_end_nonexistent_session(
        self, client: AsyncClient
    ) -> None:
        """Should return 404 for nonexistent session."""
        with patch(
            "app.services.conversation_memory_service.redis_client"
        ) as mock_redis:
            mock_redis.hgetall = AsyncMock(return_value={})

            response = await client.delete(
                "/api/v1/conversations/nonexistent"
            )

        assert response.status_code == 404


class TestGetMessagesEndpoint:
    """Tests for GET /api/v1/conversations/{session_id}/messages."""

    async def test_get_messages_invalid_limit(
        self, client: AsyncClient
    ) -> None:
        """Should return 422 for invalid limit parameter."""
        response = await client.get(
            "/api/v1/conversations/sess-123/messages?limit=0"
        )
        assert response.status_code == 422

    async def test_get_messages_invalid_offset(
        self, client: AsyncClient
    ) -> None:
        """Should return 422 for negative offset parameter."""
        response = await client.get(
            "/api/v1/conversations/sess-123/messages?offset=-1"
        )
        assert response.status_code == 422
