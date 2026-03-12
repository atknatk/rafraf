#!/usr/bin/env bash
# =============================================================================
# RafRaf Disaster Recovery - Backup & Restore Script
# =============================================================================
#
# Usage:
#   ./scripts/backup-restore.sh backup-pg       # PostgreSQL backup
#   ./scripts/backup-restore.sh backup-redis     # Redis RDB snapshot
#   ./scripts/backup-restore.sh backup-all       # Both PostgreSQL + Redis
#   ./scripts/backup-restore.sh restore-pg <s3_key>  # Restore PostgreSQL from S3
#   ./scripts/backup-restore.sh list [type]      # List backups (postgres/redis/all)
#   ./scripts/backup-restore.sh verify <s3_key>  # Verify backup integrity
#   ./scripts/backup-restore.sh rotate           # Remove backups older than 30 days
#   ./scripts/backup-restore.sh status           # Show backup health status
#
# Environment variables required:
#   BACKEND_URL     - Backend API URL (default: http://localhost:8000)
#   BACKUP_API_KEY  - API key for authentication
#
# For local restore without API:
#   DATABASE_URL    - PostgreSQL connection string
#   AWS_S3_BUCKET   - S3 bucket name
#   AWS_REGION      - AWS region
#
# =============================================================================

set -euo pipefail

BACKEND_URL="${BACKEND_URL:-http://localhost:8000}"
BACKUP_API_KEY="${BACKUP_API_KEY:-}"
TMP_DIR="/tmp/rafraf-restore"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

check_deps() {
    local deps=("curl" "jq")
    for dep in "${deps[@]}"; do
        if ! command -v "$dep" &>/dev/null; then
            log_error "$dep bulunamadi. Lutfen yukleyin."
            exit 1
        fi
    done
}

api_call() {
    local method="$1"
    local endpoint="$2"
    local data="${3:-}"
    local url="${BACKEND_URL}${endpoint}"

    local args=(-sf -X "$method" -H "Content-Type: application/json" --max-time 600)
    if [ -n "$BACKUP_API_KEY" ]; then
        args+=(-H "Authorization: Bearer ${BACKUP_API_KEY}")
    fi
    if [ -n "$data" ]; then
        args+=(-d "$data")
    fi

    curl "${args[@]}" "$url"
}

cmd_backup_pg() {
    log_info "PostgreSQL backup baslatiliyor..."
    local result
    result=$(api_call POST "/api/v1/backups/postgres")
    echo "$result" | jq .
    log_info "PostgreSQL backup tamamlandi."
}

cmd_backup_redis() {
    log_info "Redis snapshot baslatiliyor..."
    local result
    result=$(api_call POST "/api/v1/backups/redis")
    echo "$result" | jq .
    log_info "Redis snapshot tamamlandi."
}

cmd_backup_all() {
    cmd_backup_pg
    echo ""
    cmd_backup_redis
}

cmd_restore_pg() {
    local s3_key="$1"
    if [ -z "$s3_key" ]; then
        log_error "S3 key belirtilmedi. Kullanim: $0 restore-pg <s3_key>"
        exit 1
    fi

    # Restore requires local tools
    for dep in pg_restore aws gunzip; do
        if ! command -v "$dep" &>/dev/null; then
            log_error "$dep bulunamadi. PostgreSQL client ve AWS CLI gerekli."
            exit 1
        fi
    done

    local bucket="${AWS_S3_BUCKET:-}"
    local region="${AWS_REGION:-eu-central-1}"
    local db_url="${DATABASE_URL:-}"

    if [ -z "$bucket" ]; then
        log_error "AWS_S3_BUCKET ortam degiskeni gerekli."
        exit 1
    fi
    if [ -z "$db_url" ]; then
        log_error "DATABASE_URL ortam degiskeni gerekli."
        exit 1
    fi

    mkdir -p "$TMP_DIR"
    local gz_file="${TMP_DIR}/restore.dump.gz"
    local dump_file="${TMP_DIR}/restore.dump"

    log_info "Backup indiriliyor: s3://${bucket}/${s3_key}"
    aws s3 cp "s3://${bucket}/${s3_key}" "$gz_file" --region "$region"

    log_info "Dosya aciliyor..."
    gunzip -f "$gz_file"

    log_info "Backup dogrulaniyor..."
    pg_restore --list "$dump_file" >/dev/null 2>&1 || {
        log_error "Backup dosyasi gecersiz!"
        rm -f "$dump_file"
        exit 1
    }

    log_warn "DIKKAT: Bu islem mevcut veritabanini uzerine yazacaktir!"
    read -rp "Devam etmek istiyor musunuz? (evet/hayir): " confirm
    if [ "$confirm" != "evet" ]; then
        log_info "Restore iptal edildi."
        rm -f "$dump_file"
        exit 0
    fi

    # Parse DATABASE_URL
    local db_host db_port db_user db_name db_pass
    db_url_clean="${db_url/postgresql+asyncpg:\/\//postgresql:\/\/}"
    db_host=$(echo "$db_url_clean" | sed -n 's|.*@\([^:/]*\).*|\1|p')
    db_port=$(echo "$db_url_clean" | sed -n 's|.*:\([0-9]*\)/.*|\1|p')
    db_user=$(echo "$db_url_clean" | sed -n 's|.*://\([^:]*\):.*|\1|p')
    db_pass=$(echo "$db_url_clean" | sed -n 's|.*://[^:]*:\([^@]*\)@.*|\1|p')
    db_name=$(echo "$db_url_clean" | sed -n 's|.*/\([^?]*\).*|\1|p')

    log_info "Restore baslatiliyor: ${db_name}@${db_host}:${db_port}"
    export PGPASSWORD="$db_pass"

    pg_restore \
        --host="$db_host" \
        --port="${db_port:-5432}" \
        --username="$db_user" \
        --dbname="$db_name" \
        --clean \
        --if-exists \
        --no-owner \
        --no-privileges \
        "$dump_file"

    unset PGPASSWORD
    rm -f "$dump_file"

    log_info "PostgreSQL restore tamamlandi."
}

cmd_list() {
    local backup_type="${1:-all}"
    log_info "Backup listesi aliniyor (tip: ${backup_type})..."
    local result
    result=$(api_call GET "/api/v1/backups/list?backup_type=${backup_type}")
    echo "$result" | jq .
}

cmd_verify() {
    local s3_key="$1"
    if [ -z "$s3_key" ]; then
        log_error "S3 key belirtilmedi. Kullanim: $0 verify <s3_key>"
        exit 1
    fi

    log_info "Backup dogrulaniyor: ${s3_key}"
    local result
    result=$(api_call POST "/api/v1/backups/verify" "{\"s3_key\": \"${s3_key}\"}")
    echo "$result" | jq .
}

cmd_rotate() {
    log_info "Eski backup'lar siliniyor (30 gun oncesi)..."
    local result
    result=$(api_call POST "/api/v1/backups/rotate")
    echo "$result" | jq .
    log_info "Rotasyon tamamlandi."
}

cmd_status() {
    log_info "Backup durumu kontrol ediliyor..."
    local result
    result=$(api_call GET "/api/v1/backups/status")
    echo "$result" | jq .
}

# Main
check_deps

case "${1:-help}" in
    backup-pg)    cmd_backup_pg ;;
    backup-redis) cmd_backup_redis ;;
    backup-all)   cmd_backup_all ;;
    restore-pg)   cmd_restore_pg "${2:-}" ;;
    list)         cmd_list "${2:-all}" ;;
    verify)       cmd_verify "${2:-}" ;;
    rotate)       cmd_rotate ;;
    status)       cmd_status ;;
    help|*)
        echo "RafRaf Disaster Recovery"
        echo ""
        echo "Kullanim: $0 <komut> [arguman]"
        echo ""
        echo "Komutlar:"
        echo "  backup-pg          PostgreSQL backup olustur"
        echo "  backup-redis       Redis snapshot olustur"
        echo "  backup-all         Tum backup'lari olustur"
        echo "  restore-pg <key>   PostgreSQL geri yukle"
        echo "  list [tip]         Backup listesi (postgres/redis/all)"
        echo "  verify <key>       Backup butunlugunu dogrula"
        echo "  rotate             Eski backup'lari sil"
        echo "  status             Backup durumunu goster"
        ;;
esac
