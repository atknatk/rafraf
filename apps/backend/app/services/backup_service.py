"""Disaster recovery backup service - pg_dump, S3 upload, rotation, Redis snapshot."""

import asyncio
import gzip
import os
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import structlog

from app.core.config import get_settings
from app.services.s3_service import S3Service, S3ServiceError

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

# Backup retention: 30 days
_BACKUP_RETENTION_DAYS = 30

# S3 prefix for backups
_BACKUP_S3_PREFIX = "backups"

# Temporary directory for local backup files
_BACKUP_TMP_DIR = "/tmp/rafraf-backups"


class BackupError(Exception):
    """Raised when a backup operation fails."""

    def __init__(self, message: str, operation: str = "") -> None:
        self.operation = operation
        super().__init__(message)


class BackupService:
    """Handles PostgreSQL backups, S3 upload, rotation, and Redis snapshots.

    Backup flow:
    1. Run pg_dump --format=custom to create a local backup file
    2. Gzip compress the backup
    3. Upload compressed backup to S3 under backups/postgres/
    4. Clean up local temp file
    5. Rotate old backups (remove S3 objects older than 30 days)

    Redis flow:
    1. Trigger BGSAVE via redis-cli
    2. Copy RDB file, compress, upload to S3

    Restore flow (documented):
    1. Download backup from S3
    2. Decompress
    3. Run pg_restore
    """

    def __init__(self) -> None:
        self._s3_service = S3Service()
        self._settings = get_settings()
        self._tmp_dir = Path(_BACKUP_TMP_DIR)

    def _ensure_tmp_dir(self) -> None:
        """Create temporary backup directory if it doesn't exist."""
        self._tmp_dir.mkdir(parents=True, exist_ok=True)

    def _parse_db_url(self) -> dict[str, str]:
        """Parse DATABASE_URL into connection parameters.

        Returns:
            Dict with host, port, user, password, dbname keys.
        """
        db_url = self._settings.database_url
        # Handle asyncpg:// prefix — convert to postgresql://
        url_str = db_url.replace("postgresql+asyncpg://", "postgresql://")
        parsed = urlparse(url_str)

        return {
            "host": parsed.hostname or "localhost",
            "port": str(parsed.port or 5432),
            "user": parsed.username or "postgres",
            "password": parsed.password or "",
            "dbname": parsed.path.lstrip("/") if parsed.path else "rafraf",
        }

    def _generate_backup_filename(self, backup_type: str) -> str:
        """Generate a timestamped backup filename.

        Args:
            backup_type: Type of backup (postgres, redis).

        Returns:
            Filename string like 'postgres_2026-03-13T120000Z.dump.gz'.
        """
        now = datetime.now(UTC)
        timestamp = now.strftime("%Y-%m-%dT%H%M%SZ")
        extension = "dump.gz" if backup_type == "postgres" else "rdb.gz"
        return f"{backup_type}_{timestamp}.{extension}"

    async def create_postgres_backup(self) -> dict[str, str]:
        """Create a PostgreSQL backup using pg_dump and upload to S3.

        Returns:
            Dict with backup metadata (s3_key, size, timestamp, duration).

        Raises:
            BackupError: On pg_dump failure, compression failure, or S3 upload failure.
        """
        self._ensure_tmp_dir()
        db_params = self._parse_db_url()
        filename = self._generate_backup_filename("postgres")
        dump_path = self._tmp_dir / filename.replace(".gz", "")
        gz_path = self._tmp_dir / filename

        start_time = datetime.now(UTC)

        await logger.ainfo(
            "backup_postgres_started",
            host=db_params["host"],
            dbname=db_params["dbname"],
        )

        try:
            # Step 1: Run pg_dump
            env = os.environ.copy()
            env["PGPASSWORD"] = db_params["password"]

            process = await asyncio.create_subprocess_exec(
                "pg_dump",
                "--format=custom",
                f"--host={db_params['host']}",
                f"--port={db_params['port']}",
                f"--username={db_params['user']}",
                f"--dbname={db_params['dbname']}",
                f"--file={dump_path}",
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                error_msg = stderr.decode("utf-8", errors="replace")
                raise BackupError(
                    f"pg_dump basarisiz (exit code {process.returncode}): {error_msg}",
                    operation="pg_dump",
                )

            # Step 2: Gzip compress
            await self._gzip_compress(dump_path, gz_path)

            # Step 3: Upload to S3
            gz_content = gz_path.read_bytes()
            s3_key = f"{_BACKUP_S3_PREFIX}/postgres/{filename}"

            session = self._s3_service._get_session()
            async with session.client("s3") as s3:
                await s3.put_object(
                    Bucket=self._s3_service._bucket,
                    Key=s3_key,
                    Body=gz_content,
                    ContentType="application/gzip",
                    Metadata={
                        "backup-type": "postgres",
                        "database": db_params["dbname"],
                        "timestamp": start_time.isoformat(),
                    },
                )

            end_time = datetime.now(UTC)
            duration = (end_time - start_time).total_seconds()
            file_size = len(gz_content)

            await logger.ainfo(
                "backup_postgres_completed",
                s3_key=s3_key,
                size_bytes=file_size,
                duration_seconds=duration,
            )

            return {
                "status": "success",
                "backup_type": "postgres",
                "s3_key": s3_key,
                "size_bytes": str(file_size),
                "timestamp": start_time.isoformat(),
                "duration_seconds": f"{duration:.1f}",
                "database": db_params["dbname"],
            }

        except BackupError:
            raise
        except S3ServiceError as exc:
            raise BackupError(
                f"S3 yukleme hatasi: {exc}",
                operation="s3_upload",
            ) from exc
        except Exception as exc:
            raise BackupError(
                f"Beklenmeyen backup hatasi: {exc}",
                operation="postgres_backup",
            ) from exc
        finally:
            # Cleanup local files
            if dump_path.exists():
                dump_path.unlink()
            if gz_path.exists():
                gz_path.unlink()

    async def create_redis_snapshot(self) -> dict[str, str]:
        """Trigger Redis BGSAVE and upload RDB snapshot to S3.

        Returns:
            Dict with snapshot metadata.

        Raises:
            BackupError: On Redis snapshot or S3 upload failure.
        """
        self._ensure_tmp_dir()
        start_time = datetime.now(UTC)
        filename = self._generate_backup_filename("redis")

        await logger.ainfo("backup_redis_started")

        try:
            # Parse Redis URL for host/port
            redis_url = self._settings.redis_url
            parsed = urlparse(redis_url)
            redis_host = parsed.hostname or "localhost"
            redis_port = str(parsed.port or 6379)

            # Trigger BGSAVE
            process = await asyncio.create_subprocess_exec(
                "redis-cli",
                "-h", redis_host,
                "-p", redis_port,
                "BGSAVE",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                error_msg = stderr.decode("utf-8", errors="replace")
                raise BackupError(
                    f"redis-cli BGSAVE basarisiz: {error_msg}",
                    operation="redis_bgsave",
                )

            # Wait for BGSAVE to complete
            await asyncio.sleep(2)

            # Get RDB file path from CONFIG
            process = await asyncio.create_subprocess_exec(
                "redis-cli",
                "-h", redis_host,
                "-p", redis_port,
                "CONFIG", "GET", "dir",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_dir, _ = await process.communicate()
            dir_output = stdout_dir.decode("utf-8").strip().split("\n")
            redis_dir = dir_output[-1] if len(dir_output) >= 2 else "/data"

            process = await asyncio.create_subprocess_exec(
                "redis-cli",
                "-h", redis_host,
                "-p", redis_port,
                "CONFIG", "GET", "dbfilename",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_file, _ = await process.communicate()
            file_output = stdout_file.decode("utf-8").strip().split("\n")
            redis_filename = file_output[-1] if len(file_output) >= 2 else "dump.rdb"

            rdb_path = Path(redis_dir) / redis_filename
            if not rdb_path.exists():
                raise BackupError(
                    f"Redis RDB dosyasi bulunamadi: {rdb_path}",
                    operation="redis_snapshot",
                )

            # Compress and upload
            gz_path = self._tmp_dir / filename
            await self._gzip_compress(rdb_path, gz_path)

            gz_content = gz_path.read_bytes()
            s3_key = f"{_BACKUP_S3_PREFIX}/redis/{filename}"

            session = self._s3_service._get_session()
            async with session.client("s3") as s3:
                await s3.put_object(
                    Bucket=self._s3_service._bucket,
                    Key=s3_key,
                    Body=gz_content,
                    ContentType="application/gzip",
                    Metadata={
                        "backup-type": "redis",
                        "timestamp": start_time.isoformat(),
                    },
                )

            end_time = datetime.now(UTC)
            duration = (end_time - start_time).total_seconds()

            await logger.ainfo(
                "backup_redis_completed",
                s3_key=s3_key,
                size_bytes=len(gz_content),
                duration_seconds=duration,
            )

            return {
                "status": "success",
                "backup_type": "redis",
                "s3_key": s3_key,
                "size_bytes": str(len(gz_content)),
                "timestamp": start_time.isoformat(),
                "duration_seconds": f"{duration:.1f}",
            }

        except BackupError:
            raise
        except Exception as exc:
            raise BackupError(
                f"Redis snapshot hatasi: {exc}",
                operation="redis_snapshot",
            ) from exc
        finally:
            gz_path_cleanup = self._tmp_dir / filename
            if gz_path_cleanup.exists():
                gz_path_cleanup.unlink()

    async def list_backups(
        self,
        backup_type: str = "all",
        max_results: int = 50,
    ) -> list[dict[str, str]]:
        """List available backups from S3.

        Args:
            backup_type: Filter by type ('postgres', 'redis', 'all').
            max_results: Maximum number of results.

        Returns:
            List of backup metadata dicts.
        """
        prefixes: list[str] = []
        if backup_type in ("postgres", "all"):
            prefixes.append(f"{_BACKUP_S3_PREFIX}/postgres/")
        if backup_type in ("redis", "all"):
            prefixes.append(f"{_BACKUP_S3_PREFIX}/redis/")

        all_backups: list[dict[str, str]] = []
        session = self._s3_service._get_session()

        for prefix in prefixes:
            try:
                async with session.client("s3") as s3:
                    response = await s3.list_objects_v2(
                        Bucket=self._s3_service._bucket,
                        Prefix=prefix,
                        MaxKeys=max_results,
                    )

                for obj in response.get("Contents", []):
                    key = str(obj.get("Key", ""))
                    last_modified = obj.get("LastModified")
                    last_modified_str = ""
                    if isinstance(last_modified, datetime):
                        last_modified_str = last_modified.isoformat()
                    elif last_modified is not None:
                        last_modified_str = str(last_modified)

                    btype = "postgres" if "/postgres/" in key else "redis"
                    all_backups.append({
                        "key": key,
                        "backup_type": btype,
                        "size_bytes": str(obj.get("Size", 0)),
                        "last_modified": last_modified_str,
                    })
            except Exception as exc:
                await logger.awarning(
                    "backup_list_error",
                    prefix=prefix,
                    error=str(exc),
                )

        # Sort by last_modified descending
        all_backups.sort(key=lambda b: b.get("last_modified", ""), reverse=True)
        return all_backups[:max_results]

    async def rotate_backups(self) -> dict[str, int]:
        """Remove backups older than retention period (30 days).

        Returns:
            Dict with counts of deleted postgres and redis backups.
        """
        cutoff = datetime.now(UTC).timestamp() - (_BACKUP_RETENTION_DAYS * 86400)
        deleted_counts: dict[str, int] = {"postgres": 0, "redis": 0}

        for btype in ("postgres", "redis"):
            prefix = f"{_BACKUP_S3_PREFIX}/{btype}/"
            try:
                session = self._s3_service._get_session()
                async with session.client("s3") as s3:
                    response = await s3.list_objects_v2(
                        Bucket=self._s3_service._bucket,
                        Prefix=prefix,
                        MaxKeys=1000,
                    )

                    for obj in response.get("Contents", []):
                        last_modified = obj.get("LastModified")
                        if isinstance(last_modified, datetime):
                            obj_timestamp = last_modified.timestamp()
                        else:
                            continue

                        if obj_timestamp < cutoff:
                            key = str(obj.get("Key", ""))
                            await s3.delete_object(
                                Bucket=self._s3_service._bucket,
                                Key=key,
                            )
                            deleted_counts[btype] += 1
                            await logger.ainfo(
                                "backup_rotated",
                                key=key,
                                backup_type=btype,
                            )

            except Exception as exc:
                await logger.awarning(
                    "backup_rotation_error",
                    backup_type=btype,
                    error=str(exc),
                )

        await logger.ainfo(
            "backup_rotation_completed",
            deleted_postgres=deleted_counts["postgres"],
            deleted_redis=deleted_counts["redis"],
        )

        return deleted_counts

    async def verify_backup(self, s3_key: str) -> dict[str, str]:
        """Verify a backup by downloading and checking integrity.

        Args:
            s3_key: The S3 key of the backup to verify.

        Returns:
            Dict with verification result.

        Raises:
            BackupError: If backup cannot be verified.
        """
        self._ensure_tmp_dir()

        try:
            session = self._s3_service._get_session()
            async with session.client("s3") as s3:
                response = await s3.get_object(
                    Bucket=self._s3_service._bucket,
                    Key=s3_key,
                )
                body: bytes = await response["Body"].read()

            # Verify gzip integrity
            try:
                decompressed = gzip.decompress(body)
            except gzip.BadGzipFile as exc:
                return {
                    "status": "failed",
                    "s3_key": s3_key,
                    "error": f"Gzip bozuk: {exc}",
                }

            # For postgres backups, verify pg_restore can read the header
            if "/postgres/" in s3_key:
                tmp_file = self._tmp_dir / "verify_dump.tmp"
                try:
                    tmp_file.write_bytes(decompressed)

                    process = await asyncio.create_subprocess_exec(
                        "pg_restore",
                        "--list",
                        str(tmp_file),
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    _, stderr = await process.communicate()

                    if process.returncode != 0:
                        error_msg = stderr.decode("utf-8", errors="replace")
                        return {
                            "status": "failed",
                            "s3_key": s3_key,
                            "error": f"pg_restore dogrulama basarisiz: {error_msg}",
                        }
                finally:
                    if tmp_file.exists():
                        tmp_file.unlink()

            await logger.ainfo(
                "backup_verified",
                s3_key=s3_key,
                compressed_size=len(body),
                decompressed_size=len(decompressed),
            )

            return {
                "status": "verified",
                "s3_key": s3_key,
                "compressed_size_bytes": str(len(body)),
                "decompressed_size_bytes": str(len(decompressed)),
            }

        except BackupError:
            raise
        except Exception as exc:
            raise BackupError(
                f"Backup dogrulama hatasi: {exc}",
                operation="verify_backup",
            ) from exc

    async def get_backup_status(self) -> dict[str, str | list[dict[str, str]]]:
        """Get overall backup status including latest backups and health.

        Returns:
            Dict with overall status, latest backups, and retention info.
        """
        recent_backups = await self.list_backups(max_results=10)

        latest_postgres: dict[str, str] | None = None
        latest_redis: dict[str, str] | None = None

        for backup in recent_backups:
            if backup["backup_type"] == "postgres" and latest_postgres is None:
                latest_postgres = backup
            elif backup["backup_type"] == "redis" and latest_redis is None:
                latest_redis = backup
            if latest_postgres and latest_redis:
                break

        # Determine health status
        health = "healthy"
        issues: list[str] = []

        if latest_postgres is None:
            health = "warning"
            issues.append("PostgreSQL backup bulunamadi")

        if latest_redis is None:
            health = "warning"
            issues.append("Redis backup bulunamadi")

        return {
            "health": health,
            "retention_days": str(_BACKUP_RETENTION_DAYS),
            "issues": ", ".join(issues) if issues else "none",
            "latest_postgres": latest_postgres or {"status": "no_backup"},
            "latest_redis": latest_redis or {"status": "no_backup"},
            "recent_backups": recent_backups,
        }

    @staticmethod
    async def _gzip_compress(source: Path, destination: Path) -> None:
        """Compress a file using gzip.

        Args:
            source: Path to the uncompressed file.
            destination: Path for the compressed output.
        """
        content = source.read_bytes()
        compressed = gzip.compress(content, compresslevel=6)
        destination.write_bytes(compressed)


# Module-level singleton
backup_service = BackupService()
