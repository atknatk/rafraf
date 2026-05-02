"""Unit tests for liveness, readiness, and detailed health endpoints."""

from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
def mock_db() -> AsyncMock:
    """Mock AsyncSession that succeeds SELECT 1."""
    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock(return_value=MagicMock())
    return session


@contextmanager
def _client_with_db(mock_db_obj: AsyncMock) -> Iterator[TestClient]:
    """Yield a TestClient with ``get_db`` overridden, cleaning up on exit.

    Using a context manager ensures the dependency override is removed even
    if the test body raises — without this, leaked overrides bleed into
    sibling tests via the shared ``app`` instance.
    """
    from app.api.deps import get_db
    from app.main import app

    async def override_get_db() -> AsyncIterator[AsyncMock]:
        yield mock_db_obj

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# /health (liveness)
# ---------------------------------------------------------------------------


def test_health_returns_200_with_static_payload() -> None:
    """Liveness probe must succeed without touching any external dependency."""
    # Deliberately wire DB / Redis to FAIL — the liveness probe must still
    # return 200 because Kubernetes uses it to decide kill/restart and a
    # transient dep failure must not cycle a healthy pod.
    mock_db_fail = AsyncMock(spec=AsyncSession)
    mock_db_fail.execute = AsyncMock(side_effect=Exception("db down"))
    with (
        _client_with_db(mock_db_fail) as client,
        patch(
            "app.api.routes.health.redis_client._get_client",
            new=AsyncMock(side_effect=ConnectionError("redis down")),
        ),
    ):
        response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "rafraf-backend"
    assert "version" in body
    assert isinstance(body["version"], str)


def test_healthz_alias_returns_pydantic_payload(mock_db: AsyncMock) -> None:
    """``/healthz`` is the Pydantic-validated alias of ``/health``."""
    with _client_with_db(mock_db) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "version" in body


# ---------------------------------------------------------------------------
# /ready (readiness)
# ---------------------------------------------------------------------------


def _patch_bridge_online(online: bool) -> object:
    """Build a patcher whose mocked ``list_agents`` reports the given state."""
    bridge_response = MagicMock()
    bridge_response.online_count = 1 if online else 0
    return patch(
        "app.api.routes.health.bridge_registry.list_agents",
        new=AsyncMock(return_value=bridge_response),
    )


def test_ready_returns_200_when_db_and_redis_up(mock_db: AsyncMock) -> None:
    """Happy path: DB + Redis healthy, bridge gate disabled (default)."""
    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(return_value=True)

    with (
        _client_with_db(mock_db) as client,
        patch(
            "app.api.routes.health.redis_client._get_client",
            new=AsyncMock(return_value=mock_redis),
        ),
        _patch_bridge_online(False),
    ):
        response = client.get("/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    checks = body["checks"]
    assert checks["db"] is True
    assert checks["redis"] is True
    # Bridge present in payload regardless of gate so operators can see it.
    assert checks["bridge"] is False


def test_ready_returns_503_when_db_down() -> None:
    """DB ``OperationalError`` should drop readiness with per-check status."""
    mock_db_fail = AsyncMock(spec=AsyncSession)
    mock_db_fail.execute = AsyncMock(side_effect=Exception("operational error"))

    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(return_value=True)

    with (
        _client_with_db(mock_db_fail) as client,
        patch(
            "app.api.routes.health.redis_client._get_client",
            new=AsyncMock(return_value=mock_redis),
        ),
        _patch_bridge_online(True),
    ):
        response = client.get("/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["db"] is False
    assert body["checks"]["redis"] is True


def test_ready_returns_503_when_redis_ping_fails(mock_db: AsyncMock) -> None:
    """Redis ping failure (driver exception) yields 503 with redis=false."""
    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(side_effect=ConnectionError("redis ping failed"))

    with (
        _client_with_db(mock_db) as client,
        patch(
            "app.api.routes.health.redis_client._get_client",
            new=AsyncMock(return_value=mock_redis),
        ),
        _patch_bridge_online(True),
    ):
        response = client.get("/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["checks"]["db"] is True
    assert body["checks"]["redis"] is False


def test_ready_payload_includes_per_check_booleans(mock_db: AsyncMock) -> None:
    """Payload always exposes the same key set for stable monitoring queries."""
    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(return_value=True)

    with (
        _client_with_db(mock_db) as client,
        patch(
            "app.api.routes.health.redis_client._get_client",
            new=AsyncMock(return_value=mock_redis),
        ),
        _patch_bridge_online(True),
    ):
        response = client.get("/ready")

    assert response.status_code == 200
    checks = response.json()["checks"]
    # Stable schema — each value is a plain bool.
    assert set(checks.keys()) == {"db", "redis", "bridge"}
    assert all(isinstance(v, bool) for v in checks.values())


def test_ready_503_when_bridge_required_but_none_online(
    mock_db: AsyncMock,
) -> None:
    """With ``READY_REQUIRES_BRIDGE=true``, no online bridge -> 503."""
    from app.core.config import get_settings

    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(return_value=True)

    settings = get_settings()
    original = settings.ready_requires_bridge
    settings.ready_requires_bridge = True
    try:
        with (
            _client_with_db(mock_db) as client,
            patch(
                "app.api.routes.health.redis_client._get_client",
                new=AsyncMock(return_value=mock_redis),
            ),
            _patch_bridge_online(False),
        ):
            response = client.get("/ready")
    finally:
        settings.ready_requires_bridge = original

    assert response.status_code == 503
    body = response.json()
    assert body["checks"]["db"] is True
    assert body["checks"]["redis"] is True
    assert body["checks"]["bridge"] is False


def test_ready_200_when_bridge_required_and_online(mock_db: AsyncMock) -> None:
    """With ``READY_REQUIRES_BRIDGE=true``, an online bridge -> 200."""
    from app.core.config import get_settings

    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(return_value=True)

    settings = get_settings()
    original = settings.ready_requires_bridge
    settings.ready_requires_bridge = True
    try:
        with (
            _client_with_db(mock_db) as client,
            patch(
                "app.api.routes.health.redis_client._get_client",
                new=AsyncMock(return_value=mock_redis),
            ),
            _patch_bridge_online(True),
        ):
            response = client.get("/ready")
    finally:
        settings.ready_requires_bridge = original

    assert response.status_code == 200
    assert response.json()["checks"]["bridge"] is True


# ---------------------------------------------------------------------------
# /api/v1/health/detailed (operator dashboard) — preserved coverage.
# ---------------------------------------------------------------------------


def test_detailed_health_returns_200(mock_db: AsyncMock) -> None:
    """All components up -> overall 'healthy', 200."""
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
        _client_with_db(mock_db) as client,
    ):
        mock_manager.active_count = 3
        response = client.get("/api/v1/health/detailed")

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
    """Redis unavailable -> overall 'degraded' but endpoint still 200."""
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
        _client_with_db(mock_db) as client,
    ):
        mock_manager.active_count = 0
        response = client.get("/api/v1/health/detailed")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "degraded"
    assert data["components"]["redis"]["status"] == "down"
    assert data["components"]["claude_code"]["available"] is False


def test_detailed_health_unhealthy_when_db_and_redis_down() -> None:
    """Both critical deps down -> overall 'unhealthy', endpoint still 200."""
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
        _client_with_db(mock_db_fail) as client,
    ):
        mock_manager.active_count = 0
        response = client.get("/api/v1/health/detailed")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "unhealthy"
    assert data["components"]["database"]["status"] == "down"
    assert data["components"]["redis"]["status"] == "down"
