"""Unit tests for backup Pydantic schemas."""

import pytest
from pydantic import ValidationError

from app.schemas.backup import (
    BackupListItem,
    BackupListResponse,
    BackupResponse,
    BackupRotationResponse,
    BackupStatusResponse,
    BackupVerifyRequest,
    BackupVerifyResponse,
)


class TestBackupResponse:
    """Tests for BackupResponse schema."""

    def test_valid_response(self) -> None:
        """Should create valid BackupResponse."""
        resp = BackupResponse(
            status="success",
            backup_type="postgres",
            s3_key="backups/postgres/test.dump.gz",
            size_bytes="1024",
            timestamp="2026-03-13T00:00:00+00:00",
            duration_seconds="5.0",
            database="rafraf",
        )
        assert resp.status == "success"
        assert resp.backup_type == "postgres"

    def test_missing_required_field(self) -> None:
        """Should raise ValidationError for missing required field."""
        with pytest.raises(ValidationError):
            BackupResponse(
                status="success",
                # missing backup_type
                s3_key="test",
                size_bytes="0",
                timestamp="t",
                duration_seconds="0",
            )  # type: ignore[call-arg]


class TestBackupListItem:
    """Tests for BackupListItem schema."""

    def test_valid_item(self) -> None:
        """Should create valid BackupListItem."""
        item = BackupListItem(
            key="backups/postgres/test.dump.gz",
            backup_type="postgres",
            size_bytes="2048",
            last_modified="2026-03-13T00:00:00",
        )
        assert item.key == "backups/postgres/test.dump.gz"
        assert item.backup_type == "postgres"


class TestBackupListResponse:
    """Tests for BackupListResponse schema."""

    def test_empty_list(self) -> None:
        """Should handle empty backup list."""
        resp = BackupListResponse(backups=[], total=0)
        assert resp.total == 0
        assert len(resp.backups) == 0

    def test_with_items(self) -> None:
        """Should handle list with items."""
        items = [
            BackupListItem(
                key="backups/postgres/a.dump.gz",
                backup_type="postgres",
                size_bytes="1024",
                last_modified="2026-03-13T00:00:00",
            ),
        ]
        resp = BackupListResponse(backups=items, total=1)
        assert resp.total == 1


class TestBackupRotationResponse:
    """Tests for BackupRotationResponse schema."""

    def test_valid_rotation(self) -> None:
        """Should create valid rotation response."""
        resp = BackupRotationResponse(
            postgres_deleted=5,
            redis_deleted=2,
            retention_days=30,
        )
        assert resp.postgres_deleted == 5
        assert resp.retention_days == 30


class TestBackupVerifyRequest:
    """Tests for BackupVerifyRequest schema."""

    def test_valid_request(self) -> None:
        """Should create valid verify request."""
        req = BackupVerifyRequest(s3_key="backups/postgres/test.dump.gz")
        assert req.s3_key == "backups/postgres/test.dump.gz"


class TestBackupVerifyResponse:
    """Tests for BackupVerifyResponse schema."""

    def test_verified_response(self) -> None:
        """Should create verified response."""
        resp = BackupVerifyResponse(
            status="verified",
            s3_key="backups/postgres/test.dump.gz",
            compressed_size_bytes="500",
            decompressed_size_bytes="2000",
        )
        assert resp.status == "verified"

    def test_failed_response(self) -> None:
        """Should create failed response with error."""
        resp = BackupVerifyResponse(
            status="failed",
            s3_key="bad-key",
            error="Gzip bozuk",
        )
        assert resp.status == "failed"
        assert resp.error == "Gzip bozuk"


class TestBackupStatusResponse:
    """Tests for BackupStatusResponse schema."""

    def test_healthy_status(self) -> None:
        """Should create healthy status response."""
        resp = BackupStatusResponse(
            health="healthy",
            retention_days="30",
            issues="none",
            latest_postgres={"key": "test.dump.gz"},
            latest_redis={"key": "test.rdb.gz"},
            recent_backups=[],
        )
        assert resp.health == "healthy"
        assert resp.issues == "none"
