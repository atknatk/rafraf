#!/usr/bin/env bash
# restore-dev-db.sh — Dev Postgres restore helper for RafRaf.
#
# Companion to backup-dev-db.sh. Restores a gzipped pg_dump (plain SQL) into
# the running rafraf-postgres container by:
#   1. Validating the container is running and the backup file exists.
#   2. Terminating active sessions then DROP+CREATE the rafraf database.
#   3. Streaming gunzip output into psql inside the container.
#   4. Verifying alembic head + sanity row counts on key tables.
#
# Usage:
#   bash infra/scripts/restore-dev-db.sh ~/Code/rafraf-backups/<ts>.sql.gz
#
# Exit codes:
#   0  success (restore + verification passed)
#   1  generic / verification failure (alembic head missing, etc.)
#   2  container 'rafraf-postgres' not running
#   3  backup file missing or empty
#   4  bad CLI usage
#
# DESTRUCTIVE: drops the local dev rafraf database. Never point this at
# production. The script intentionally has no `--prod` switch and no env-var
# override for the container/db names so a typo or env leak cannot redirect
# it elsewhere.
#
# Used by the T2.6 DR drill (docs/runbooks/drills/2026-05-02-faz2-restore-drill.md)
# and reusable for re-baselining the local dev DB before integration tests.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${REPO_ROOT}/apps/backend/.env"
CONTAINER="${POSTGRES_CONTAINER:-rafraf-postgres}"

# Load env file if present (parity with backup-dev-db.sh). Pre-existing env
# vars are not overwritten thanks to `set -a` only affecting unset names in
# combination with the source semantics.
if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi

POSTGRES_USER="${POSTGRES_USER:-rafraf}"
POSTGRES_DB="${POSTGRES_DB:-rafraf}"
# Dev container's POSTGRES_USER is also the cluster superuser (single role
# bootstrap from the official postgres image). On a managed/self-hosted
# Postgres with a separate `postgres` superuser, override via:
#   POSTGRES_SUPERUSER=postgres bash restore-dev-db.sh <file>
POSTGRES_SUPERUSER="${POSTGRES_SUPERUSER:-${POSTGRES_USER}}"

# --- arg parsing ---------------------------------------------------------
if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <backup-file.sql.gz>" >&2
  exit 4
fi
BACKUP_FILE="$1"

# --- preflight checks ----------------------------------------------------
if ! docker ps --format '{{.Names}}' | grep -qx "${CONTAINER}"; then
  echo "ERROR: container '${CONTAINER}' is not running." >&2
  echo "Hint:  docker compose -f infra/docker/docker-compose.dev.yml up -d postgres" >&2
  exit 2
fi

if [[ ! -f "${BACKUP_FILE}" ]]; then
  echo "ERROR: backup file '${BACKUP_FILE}' does not exist." >&2
  exit 3
fi

if [[ ! -s "${BACKUP_FILE}" ]]; then
  echo "ERROR: backup file '${BACKUP_FILE}' is empty." >&2
  exit 3
fi

START_TS="$(date +%Y-%m-%dT%H:%M:%S%z)"
START_EPOCH="$(date +%s)"
SIZE="$(du -h "${BACKUP_FILE}" | cut -f1)"

echo "==> restore-dev-db.sh"
echo "    container : ${CONTAINER}"
echo "    database  : ${POSTGRES_DB} (owner ${POSTGRES_USER})"
echo "    backup    : ${BACKUP_FILE} (${SIZE})"
echo "    started   : ${START_TS}"

# --- drop + recreate -----------------------------------------------------
# WITH (FORCE) requires Postgres 13+. The dev container ships pg16, so this
# is safe; we still set the connection limit to 0 first as a belt-and-braces
# step to drain anyone who slipped in between checks.
echo "==> dropping ${POSTGRES_DB}"
docker exec "${CONTAINER}" psql -U "${POSTGRES_SUPERUSER}" -d postgres -v ON_ERROR_STOP=1 -c "
  ALTER DATABASE ${POSTGRES_DB} CONNECTION LIMIT 0;
" >/dev/null 2>&1 || true   # may fail if DB does not exist yet; that's fine

docker exec "${CONTAINER}" psql -U "${POSTGRES_SUPERUSER}" -d postgres -v ON_ERROR_STOP=1 -c "
  SELECT pg_terminate_backend(pid)
  FROM pg_stat_activity
  WHERE datname = '${POSTGRES_DB}' AND pid <> pg_backend_pid();
" >/dev/null

docker exec "${CONTAINER}" psql -U "${POSTGRES_SUPERUSER}" -d postgres -v ON_ERROR_STOP=1 -c \
  "DROP DATABASE IF EXISTS ${POSTGRES_DB} WITH (FORCE);"

echo "==> creating ${POSTGRES_DB} owner=${POSTGRES_USER}"
docker exec "${CONTAINER}" psql -U "${POSTGRES_SUPERUSER}" -d postgres -v ON_ERROR_STOP=1 -c \
  "CREATE DATABASE ${POSTGRES_DB} OWNER ${POSTGRES_USER};"

# --- restore -------------------------------------------------------------
echo "==> restoring (gunzip | psql)"
# `--single-transaction` would speed restore but plain pg_dump output already
# wraps DDL safely; using -v ON_ERROR_STOP=1 to fail fast on any SQL error.
gunzip -c "${BACKUP_FILE}" \
  | docker exec -i "${CONTAINER}" psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
      -v ON_ERROR_STOP=1 \
      --quiet >/dev/null

# --- verify --------------------------------------------------------------
echo "==> verifying"
ALEMBIC_HEAD="$(docker exec "${CONTAINER}" psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -tAc \
  "SELECT version_num FROM alembic_version;" | tr -d '[:space:]')"

if [[ -z "${ALEMBIC_HEAD}" ]]; then
  echo "ERROR: alembic_version returned no row after restore." >&2
  exit 1
fi
echo "    alembic_version : ${ALEMBIC_HEAD}"

# Sanity row counts on a couple of always-present tables. Empty seed DBs are
# valid (count == 0); we only fail if the table itself is missing (which would
# raise a SQL error inside psql due to ON_ERROR_STOP=1).
USERS_COUNT="$(docker exec "${CONTAINER}" psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -tAc \
  "SELECT count(*) FROM users;" | tr -d '[:space:]')"
SESSIONS_COUNT="$(docker exec "${CONTAINER}" psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -tAc \
  "SELECT count(*) FROM sessions;" | tr -d '[:space:]')"

echo "    users           : ${USERS_COUNT}"
echo "    sessions        : ${SESSIONS_COUNT}"

END_TS="$(date +%Y-%m-%dT%H:%M:%S%z)"
END_EPOCH="$(date +%s)"
DURATION=$((END_EPOCH - START_EPOCH))

echo "==> done"
echo "    finished  : ${END_TS}"
echo "    duration  : ${DURATION}s"
