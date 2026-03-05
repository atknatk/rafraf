"""Unit tests for the detailed health endpoint."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture()
def mock_db() -> AsyncMock:
    """Mock AsyncSession that succeeds SELECT 1."""
    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock(return_value=MagicMock())
    return session


def _make_client(mock_db: AsyncMock) -> TestClient:
    """Create a TestClient with mocked DB, Redis, and system deps."""
    from app.main import app
    from app.api.deps import get_db

    async def override_get_db() -> AsyncMock:  # type: ignore[misc]
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def test_detailed_health_returns_200(mock_db: AsyncMock) -> None:
    """GET /api/v1/health/detailed should return 200 with healthy status when all components up."""
    mock_redis_client = AsyncMock()
    mock_redis_client.ping = AsyncMock(return_value=True)

    mock_mem = MagicMock()
    mock_mem.percent = 45.2
    mock_mem.used = 1823 * 1024 * 1024

    with (
        patch(
            "app.api.routes.health.redis_client._get_client",
            new=AsyncMock(return_value=mock_redis_client),
        ),
        patch("app.api.routes.health.psutil.virtual_memory", return_value=mock_mem),
        patch("app.api.routes.health.psutil.cpu_percent", return_value=12.1),
        patch("app.api.routes.health.shutil.which", return_value="/usr/local/bin/claude"),
        patch("app.api.routes.health.manager") as mock_manager,
    ):
        mock_manager.active_count = 3
        client = _make_client(mock_db)
        try:
            response = client.get("/api/v1/health/detailed")
        finally:
            from app.main import app
            app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "timestamp" in data
    components = data["components"]
    assert components["database"]["status"] == "up"
    assert components["redis"]["status"] == "up"
    assert components["websocket"]["active_connections"] == 3
    assert components["system"]["memory_percent"] == 45.2
    assert components["claude_code"]["available"] is True


def test_detailed_health_degraded_when_redis_down(mock_db: AsyncMock) -> None:
    """Status should be 'degraded' when Redis is unavailable."""
    mock_mem = MagicMock()
    mock_mem.percent = 30.0
    mock_mem.used = 1024 * 1024 * 1024

    with (
        patch(
            "app.api.routes.health.redis_client._get_client",
            new=AsyncMock(side_effect=ConnectionError("redis unavailable")),
        ),
        patch("app.api.routes.health.psutil.virtual_memory", return_value=mock_mem),
        patch("app.api.routes.health.psutil.cpu_percent", return_value=5.0),
        patch("app.api.routes.health.shutil.which", return_value=None),
        patch("app.api.routes.health.manager") as mock_manager,
    ):
        mock_manager.active_count = 0
        client = _make_client(mock_db)
        try:
            response = client.get("/api/v1/health/detailed")
        finally:
            from app.main import app
            app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "degraded"
    assert data["components"]["redis"]["status"] == "down"
    assert data["components"]["claude_code"]["available"] is False


def test_detailed_health_unhealthy_when_db_and_redis_down() -> None:
    """Status should be 'unhealthy' when both DB and Redis are down."""
    mock_db_fail = AsyncMock(spec=AsyncSession)
    mock_db_fail.execute = AsyncMock(side_effect=Exception("db connection error"))

    mock_mem = MagicMock()
    mock_mem.percent = 80.0
    mock_mem.used = 4096 * 1024 * 1024

    with (
        patch(
            "app.api.routes.health.redis_client._get_client",
            new=AsyncMock(side_effect=ConnectionError("redis unavailable")),
        ),
        patch("app.api.routes.health.psutil.virtual_memory", return_value=mock_mem),
        patch("app.api.routes.health.psutil.cpu_percent", return_value=90.0),
        patch("app.api.routes.health.shutil.which", return_value=None),
        patch("app.api.routes.health.manager") as mock_manager,
    ):
        mock_manager.active_count = 0
        client = _make_client(mock_db_fail)
        try:
            response = client.get("/api/v1/health/detailed")
        finally:
            from app.main import app
            app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "unhealthy"
    assert data["components"]["database"]["status"] == "down"
    assert data["components"]["redis"]["status"] == "down"
