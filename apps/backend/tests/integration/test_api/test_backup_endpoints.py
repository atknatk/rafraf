"""Integration tests for backup/disaster recovery API endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.main import app
from app.services.backup_service import BackupError

_mock_user = MagicMock()
_mock_user.id = "test-user-id"

client = TestClient(app)


@pytest.fixture(autouse=True)
def _override_auth():
    """Override auth dependency before each test, restore after."""
    app.dependency_overrides[get_current_user] = lambda: _mock_user
    yield
    app.dependency_overrides.pop(get_current_user, None)


class TestGetBackupStatus:
    """Tests for GET /api/v1/backups/status."""

    def test_status_returns_200(self) -> None:
        """Status endpoint should return 200 with health info."""
        with patch(
            "app.api.routes.backups.backup_service.get_backup_status",
            new_callable=AsyncMock,
        ) as mock_status:
            mock_status.return_value = {
                "health": "healthy",
                "retention_days": "30",
                "issues": "none",
                "latest_postgres": {"key": "backups/postgres/test.dump.gz"},
                "latest_redis": {"key": "backups/redis/test.rdb.gz"},
                "recent_backups": [],
            }

            response = client.get("/api/v1/backups/status")

        assert response.status_code == 200
        data = response.json()
        assert data["health"] == "healthy"
        assert data["retention_days"] == "30"

    def test_status_service_error_returns_500(self) -> None:
        """Status endpoint should return 500 on service error."""
        with patch(
            "app.api.routes.backups.backup_service.get_backup_status",
            new_callable=AsyncMock,
        ) as mock_status:
            mock_status.side_effect = RuntimeError("S3 unreachable")

            response = client.get("/api/v1/backups/status")

        assert response.status_code == 500


class TestCreatePostgresBackup:
    """Tests for POST /api/v1/backups/postgres."""

    def test_postgres_backup_success(self) -> None:
        """Postgres backup should return 200 with metadata."""
        with patch(
            "app.api.routes.backups.backup_service.create_postgres_backup",
            new_callable=AsyncMock,
        ) as mock_backup:
            mock_backup.return_value = {
                "status": "success",
                "backup_type": "postgres",
                "s3_key": "backups/postgres/test.dump.gz",
                "size_bytes": "1024",
                "timestamp": "2026-03-13T00:00:00+00:00",
                "duration_seconds": "5.0",
                "database": "rafraf",
            }

            response = client.post("/api/v1/backups/postgres")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["backup_type"] == "postgres"
        assert data["s3_key"].startswith("backups/postgres/")

    def test_postgres_backup_failure_returns_500(self) -> None:
        """Postgres backup failure should return 500."""
        with patch(
            "app.api.routes.backups.backup_service.create_postgres_backup",
            new_callable=AsyncMock,
        ) as mock_backup:
            mock_backup.side_effect = BackupError("pg_dump failed", operation="pg_dump")

            response = client.post("/api/v1/backups/postgres")

        assert response.status_code == 500
        assert "PostgreSQL backup basarisiz" in response.json()["detail"]


class TestCreateRedisSnapshot:
    """Tests for POST /api/v1/backups/redis."""

    def test_redis_snapshot_success(self) -> None:
        """Redis snapshot should return 200 with metadata."""
        with patch(
            "app.api.routes.backups.backup_service.create_redis_snapshot",
            new_callable=AsyncMock,
        ) as mock_backup:
            mock_backup.return_value = {
                "status": "success",
                "backup_type": "redis",
                "s3_key": "backups/redis/test.rdb.gz",
                "size_bytes": "512",
                "timestamp": "2026-03-13T00:00:00+00:00",
                "duration_seconds": "2.0",
                "database": "",
            }

            response = client.post("/api/v1/backups/redis")

        assert response.status_code == 200
        data = response.json()
        assert data["backup_type"] == "redis"


class TestListBackups:
    """Tests for GET /api/v1/backups/list."""

    def test_list_all_backups(self) -> None:
        """List endpoint should return backup list."""
        with patch(
            "app.api.routes.backups.backup_service.list_backups",
            new_callable=AsyncMock,
        ) as mock_list:
            mock_list.return_value = [
                {
                    "key": "backups/postgres/test.dump.gz",
                    "backup_type": "postgres",
                    "size_bytes": "1024",
                    "last_modified": "2026-03-13T00:00:00+00:00",
                },
            ]

            response = client.get("/api/v1/backups/list")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["backups"]) == 1

    def test_list_with_type_filter(self) -> None:
        """List endpoint should accept backup_type query param."""
        with patch(
            "app.api.routes.backups.backup_service.list_backups",
            new_callable=AsyncMock,
        ) as mock_list:
            mock_list.return_value = []

            response = client.get("/api/v1/backups/list?backup_type=postgres")

        assert response.status_code == 200
        mock_list.assert_called_once_with(backup_type="postgres", max_results=50)

    def test_list_invalid_type_returns_400(self) -> None:
        """List endpoint should return 400 for invalid backup_type."""
        response = client.get("/api/v1/backups/list?backup_type=invalid")
        assert response.status_code == 400


class TestRotateBackups:
    """Tests for POST /api/v1/backups/rotate."""

    def test_rotate_success(self) -> None:
        """Rotate endpoint should return deletion counts."""
        with patch(
            "app.api.routes.backups.backup_service.rotate_backups",
            new_callable=AsyncMock,
        ) as mock_rotate:
            mock_rotate.return_value = {"postgres": 3, "redis": 1}

            response = client.post("/api/v1/backups/rotate")

        assert response.status_code == 200
        data = response.json()
        assert data["postgres_deleted"] == 3
        assert data["redis_deleted"] == 1
        assert data["retention_days"] == 30


class TestVerifyBackup:
    """Tests for POST /api/v1/backups/verify."""

    def test_verify_success(self) -> None:
        """Verify endpoint should return verification result."""
        with patch(
            "app.api.routes.backups.backup_service.verify_backup",
            new_callable=AsyncMock,
        ) as mock_verify:
            mock_verify.return_value = {
                "status": "verified",
                "s3_key": "backups/postgres/test.dump.gz",
                "compressed_size_bytes": "500",
                "decompressed_size_bytes": "2000",
            }

            response = client.post(
                "/api/v1/backups/verify",
                json={"s3_key": "backups/postgres/test.dump.gz"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "verified"

    def test_verify_failure_returns_500(self) -> None:
        """Verify failure should return 500."""
        with patch(
            "app.api.routes.backups.backup_service.verify_backup",
            new_callable=AsyncMock,
        ) as mock_verify:
            mock_verify.side_effect = BackupError("S3 error", operation="verify")

            response = client.post(
                "/api/v1/backups/verify",
                json={"s3_key": "bad-key"},
            )

        assert response.status_code == 500
