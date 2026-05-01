#!/usr/bin/env bash
# backup-dev-db.sh — Dev Postgres backup helper for RafRaf.
#
# Runs pg_dump inside the running rafraf-postgres container (so pg_dump does
# not need to be installed on the host), gzips the output, and writes to
# ~/Code/rafraf-backups/<timestamp>.sql.gz.
#
# DB credentials are read from apps/backend/.env if present, otherwise from
# the docker-compose.dev.yml defaults (POSTGRES_USER=rafraf, DB=rafraf).
#
# Used by T0.1 pre-flight backup; reusable before any destructive schema op.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${REPO_ROOT}/apps/backend/.env"
CONTAINER="${POSTGRES_CONTAINER:-rafraf-postgres}"
BACKUP_DIR="${BACKUP_DIR:-${HOME}/Code/rafraf-backups}"

# Load env file if it exists (does not override pre-existing env vars).
if [[ -f "${ENV_FILE}" ]]; then
  # shellcheck disable=SC1090
  set -a
  source "${ENV_FILE}"
  set +a
fi

POSTGRES_USER="${POSTGRES_USER:-rafraf}"
POSTGRES_DB="${POSTGRES_DB:-rafraf}"

# Verify container is running.
if ! docker ps --format '{{.Names}}' | grep -qx "${CONTAINER}"; then
  echo "ERROR: container '${CONTAINER}' is not running." >&2
  echo "Hint: docker compose -f infra/docker/docker-compose.dev.yml up -d postgres" >&2
  exit 1
fi

mkdir -p "${BACKUP_DIR}"
TIMESTAMP="$(date +%Y-%m-%d-%H%M%S)"
OUTFILE="${BACKUP_DIR}/${TIMESTAMP}.sql.gz"

echo "Dumping ${POSTGRES_DB}@${CONTAINER} as ${POSTGRES_USER} -> ${OUTFILE}"
docker exec -t "${CONTAINER}" pg_dump -U "${POSTGRES_USER}" "${POSTGRES_DB}" \
  | gzip > "${OUTFILE}"

SIZE="$(du -h "${OUTFILE}" | cut -f1)"
echo "OK: ${OUTFILE} (${SIZE})"
