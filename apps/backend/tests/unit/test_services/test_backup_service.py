"""Unit tests for BackupService."""

import gzip
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.backup_service import BackupError, BackupService


class TestParseDbUrl:
    """Tests for BackupService._parse_db_url."""

    def test_parse_asyncpg_url(self) -> None:
        """Should parse postgresql+asyncpg:// URL correctly."""
        service = BackupService()
        with patch.object(service, "_settings") as mock_settings:
            mock_settings.database_url = (
                "postgresql+asyncpg://myuser:mypass@db.example.com:5433/mydb"
            )
            result = service._parse_db_url()

        assert result["host"] == "db.example.com"
        assert result["port"] == "5433"
        assert result["user"] == "myuser"
        assert result["password"] == "mypass"
        assert result["dbname"] == "mydb"

    def test_parse_default_port(self) -> None:
        """Should default to port 5432 when not specified."""
        service = BackupService()
        with patch.object(service, "_settings") as mock_settings:
            mock_settings.database_url = "postgresql+asyncpg://user:pass@localhost/testdb"
            result = service._parse_db_url()

        assert result["host"] == "localhost"
        assert result["port"] == "5432"
        assert result["dbname"] == "testdb"


class TestGenerateBackupFilename:
    """Tests for BackupService._generate_backup_filename."""

    def test_postgres_filename_format(self) -> None:
        """Postgres filename should end with .dump.gz."""
        service = BackupService()
        filename = service._generate_backup_filename("postgres")
        assert filename.startswith("postgres_")
        assert filename.endswith(".dump.gz")

    def test_redis_filename_format(self) -> None:
        """Redis filename should end with .rdb.gz."""
        service = BackupService()
        filename = service._generate_backup_filename("redis")
        assert filename.startswith("redis_")
        assert filename.endswith(".rdb.gz")

    def test_filename_contains_timestamp(self) -> None:
        """Filename should contain a timestamp."""
        service = BackupService()
        filename = service._generate_backup_filename("postgres")
        # Should contain date pattern like 2026-03-13
        parts = filename.split("_", 1)
        assert len(parts) == 2
        timestamp_part = parts[1].replace(".dump.gz", "")
        assert "T" in timestamp_part


class TestGzipCompress:
    """Tests for BackupService._gzip_compress."""

    async def test_compress_creates_valid_gzip(self, tmp_path: Path) -> None:
        """Compressed file should be valid gzip."""
        source = tmp_path / "source.txt"
        dest = tmp_path / "source.txt.gz"
        original_content = b"Hello, this is test data for compression!"
        source.write_bytes(original_content)

        await BackupService._gzip_compress(source, dest)

        assert dest.exists()
        decompressed = gzip.decompress(dest.read_bytes())
        assert decompressed == original_content

    async def test_compress_empty_file(self, tmp_path: Path) -> None:
        """Should handle empty file compression."""
        source = tmp_path / "empty.txt"
        dest = tmp_path / "empty.txt.gz"
        source.write_bytes(b"")

        await BackupService._gzip_compress(source, dest)

        assert dest.exists()
        decompressed = gzip.decompress(dest.read_bytes())
        assert decompressed == b""


class TestCreatePostgresBackup:
    """Tests for BackupService.create_postgres_backup."""

    async def test_backup_success(self, tmp_path: Path) -> None:
        """Successful pg_dump should upload to S3 and return metadata."""
        service = BackupService()
        service._tmp_dir = tmp_path

        with (
            patch.object(
                service,
                "_parse_db_url",
                return_value={
                    "host": "localhost",
                    "port": "5432",
                    "user": "postgres",
                    "password": "secret",
                    "dbname": "testdb",
                },
            ),
            patch("asyncio.create_subprocess_exec") as mock_exec,
        ):
            # Mock pg_dump process
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(return_value=(b"", b""))
            mock_process.returncode = 0
            mock_exec.return_value = mock_process

            # Create a fake dump file that pg_dump would produce
            async def fake_communicate() -> tuple[bytes, bytes]:
                # Simulate pg_dump creating a file
                dump_files = list(tmp_path.glob("postgres_*.dump"))
                if dump_files:
                    dump_files[0].write_bytes(b"PGDUMP_FAKE_DATA")
                return (b"", b"")

            mock_process.communicate = fake_communicate

            # Mock S3 upload
            mock_s3 = AsyncMock()
            mock_s3.put_object = AsyncMock(return_value={})
            mock_s3.__aenter__ = AsyncMock(return_value=mock_s3)
            mock_s3.__aexit__ = AsyncMock(return_value=False)

            mock_session = MagicMock()
            mock_session.client = MagicMock(return_value=mock_s3)

            with (
                patch.object(service._s3_service, "_get_session", return_value=mock_session),
                patch.object(
                    service,
                    "_gzip_compress",
                    new_callable=AsyncMock,
                ) as mock_compress,
            ):
                # We need to handle the fact that pg_dump creates the file
                # Since our mock doesn't actually create it, we need to patch _gzip_compress
                # Create a fake gz file when compress is called
                async def fake_compress(_source: Path, dest: Path) -> None:
                    dest.write_bytes(gzip.compress(b"FAKE_DATA"))

                mock_compress.side_effect = fake_compress

                result = await service.create_postgres_backup()

        assert result["status"] == "success"
        assert result["backup_type"] == "postgres"
        assert "s3_key" in result
        assert result["s3_key"].startswith("backups/postgres/")
        assert result["database"] == "testdb"

    async def test_backup_pg_dump_failure(self, tmp_path: Path) -> None:
        """Failed pg_dump should raise BackupError."""
        service = BackupService()
        service._tmp_dir = tmp_path

        with (
            patch.object(
                service,
                "_parse_db_url",
                return_value={
                    "host": "localhost",
                    "port": "5432",
                    "user": "postgres",
                    "password": "secret",
                    "dbname": "testdb",
                },
            ),
            patch("asyncio.create_subprocess_exec") as mock_exec,
        ):
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(return_value=(b"", b"pg_dump: connection refused"))
            mock_process.returncode = 1
            mock_exec.return_value = mock_process

            with pytest.raises(BackupError) as exc_info:
                await service.create_postgres_backup()

            assert "pg_dump basarisiz" in str(exc_info.value)
            assert exc_info.value.operation == "pg_dump"


class TestListBackups:
    """Tests for BackupService.list_backups."""

    async def test_list_all_backups(self) -> None:
        """Should list both postgres and redis backups."""
        service = BackupService()

        mock_s3 = AsyncMock()
        mock_s3.list_objects_v2 = AsyncMock(
            return_value={
                "Contents": [
                    {
                        "Key": "backups/postgres/postgres_2026-03-13.dump.gz",
                        "Size": 1024,
                        "LastModified": datetime(2026, 3, 13, tzinfo=UTC),
                    },
                ]
            }
        )
        mock_s3.__aenter__ = AsyncMock(return_value=mock_s3)
        mock_s3.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.client = MagicMock(return_value=mock_s3)

        with patch.object(service._s3_service, "_get_session", return_value=mock_session):
            result = await service.list_backups(backup_type="all")

        assert len(result) >= 1
        assert result[0]["backup_type"] == "postgres"

    async def test_list_empty_bucket(self) -> None:
        """Should return empty list for empty bucket."""
        service = BackupService()

        mock_s3 = AsyncMock()
        mock_s3.list_objects_v2 = AsyncMock(return_value={"Contents": []})
        mock_s3.__aenter__ = AsyncMock(return_value=mock_s3)
        mock_s3.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.client = MagicMock(return_value=mock_s3)

        with patch.object(service._s3_service, "_get_session", return_value=mock_session):
            result = await service.list_backups(backup_type="postgres")

        assert result == []


class TestRotateBackups:
    """Tests for BackupService.rotate_backups."""

    async def test_rotate_deletes_old_backups(self) -> None:
        """Should delete backups older than 30 days."""
        service = BackupService()

        old_date = datetime(2026, 1, 1, tzinfo=UTC)  # >30 days ago
        recent_date = datetime(2026, 3, 12, tzinfo=UTC)  # Recent

        mock_s3 = AsyncMock()
        mock_s3.list_objects_v2 = AsyncMock(
            return_value={
                "Contents": [
                    {
                        "Key": "backups/postgres/old_backup.dump.gz",
                        "LastModified": old_date,
                    },
                    {
                        "Key": "backups/postgres/recent_backup.dump.gz",
                        "LastModified": recent_date,
                    },
                ]
            }
        )
        mock_s3.delete_object = AsyncMock(return_value={})
        mock_s3.__aenter__ = AsyncMock(return_value=mock_s3)
        mock_s3.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.client = MagicMock(return_value=mock_s3)

        with patch.object(service._s3_service, "_get_session", return_value=mock_session):
            result = await service.rotate_backups()

        # Old backup should be deleted
        assert result["postgres"] >= 1


class TestVerifyBackup:
    """Tests for BackupService.verify_backup."""

    async def test_verify_valid_gzip(self, tmp_path: Path) -> None:
        """Should verify valid gzip file successfully."""
        service = BackupService()
        service._tmp_dir = tmp_path

        valid_gz = gzip.compress(b"VALID_DATA")

        mock_s3 = AsyncMock()
        mock_body = AsyncMock()
        mock_body.read = AsyncMock(return_value=valid_gz)
        mock_s3.get_object = AsyncMock(return_value={"Body": mock_body})
        mock_s3.__aenter__ = AsyncMock(return_value=mock_s3)
        mock_s3.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.client = MagicMock(return_value=mock_s3)

        with patch.object(service._s3_service, "_get_session", return_value=mock_session):
            result = await service.verify_backup("backups/redis/test.rdb.gz")

        assert result["status"] == "verified"

    async def test_verify_invalid_gzip(self, tmp_path: Path) -> None:
        """Should report failure for invalid gzip."""
        service = BackupService()
        service._tmp_dir = tmp_path

        mock_s3 = AsyncMock()
        mock_body = AsyncMock()
        mock_body.read = AsyncMock(return_value=b"NOT_GZIP_DATA")
        mock_s3.get_object = AsyncMock(return_value={"Body": mock_body})
        mock_s3.__aenter__ = AsyncMock(return_value=mock_s3)
        mock_s3.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.client = MagicMock(return_value=mock_s3)

        with patch.object(service._s3_service, "_get_session", return_value=mock_session):
            result = await service.verify_backup("backups/postgres/test.dump.gz")

        assert result["status"] == "failed"
        assert "Gzip bozuk" in result["error"]


class TestGetBackupStatus:
    """Tests for BackupService.get_backup_status."""

    async def test_status_no_backups(self) -> None:
        """Should return warning when no backups exist."""
        service = BackupService()

        with patch.object(service, "list_backups", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = []
            result = await service.get_backup_status()

        assert result["health"] == "warning"
        assert "PostgreSQL backup bulunamadi" in str(result["issues"])

    async def test_status_with_backups(self) -> None:
        """Should return healthy when backups exist."""
        service = BackupService()

        with patch.object(service, "list_backups", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = [
                {
                    "key": "backups/postgres/pg.dump.gz",
                    "backup_type": "postgres",
                    "size_bytes": "1024",
                    "last_modified": "2026-03-13T00:00:00+00:00",
                },
                {
                    "key": "backups/redis/redis.rdb.gz",
                    "backup_type": "redis",
                    "size_bytes": "512",
                    "last_modified": "2026-03-13T00:00:00+00:00",
                },
            ]
            result = await service.get_backup_status()

        assert result["health"] == "healthy"
        assert result["issues"] == "none"


class TestBackupError:
    """Tests for BackupError exception."""

    def test_error_with_operation(self) -> None:
        """BackupError should store operation name."""
        error = BackupError("test error", operation="pg_dump")
        assert str(error) == "test error"
        assert error.operation == "pg_dump"

    def test_error_without_operation(self) -> None:
        """BackupError should default to empty operation."""
        error = BackupError("test error")
        assert error.operation == ""
