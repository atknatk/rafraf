#!/usr/bin/env bash
set -euo pipefail

# ─────────────────────────────────────────────────────────────
# RafRaf Host Agent — Auto-Updater
#
# 5 dakikada bir calisir, repo'da degisiklik varsa:
#   git pull → pip install → agent restart
#
# Standalone kullanim:
#   bash ~/.rafraf-agent/src/scripts/agent-updater.sh
# ─────────────────────────────────────────────────────────────

INSTALL_DIR="$HOME/.rafraf-agent"
SRC_DIR="$INSTALL_DIR/src"
AGENT_SRC="$SRC_DIR/apps/agent"
VENV_PYTHON="$INSTALL_DIR/venv/bin/python"
LOG_FILE="$INSTALL_DIR/logs/updater.log"
LOCK_FILE="$INSTALL_DIR/.updater.lock"
REPO_BRANCH="develop"

# ── Logging ─────────────────────────────────────────────────
log() {
  local ts
  ts="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  echo "[$ts] $*" >> "$LOG_FILE"
}

# ── Lock (prevent concurrent runs) ──────────────────────────
acquire_lock() {
  if [ -f "$LOCK_FILE" ]; then
    local lock_pid
    lock_pid="$(cat "$LOCK_FILE" 2>/dev/null || echo "")"
    if [ -n "$lock_pid" ] && kill -0 "$lock_pid" 2>/dev/null; then
      log "SKIP: Another updater is running (PID $lock_pid)"
      exit 0
    fi
    # Stale lock
    rm -f "$LOCK_FILE"
  fi
  echo $$ > "$LOCK_FILE"
}

release_lock() {
  rm -f "$LOCK_FILE"
}

trap release_lock EXIT

# ── Pre-flight checks ───────────────────────────────────────
preflight() {
  if [ ! -d "$SRC_DIR/.git" ]; then
    log "ERROR: Repo not found at $SRC_DIR"
    exit 1
  fi

  if [ ! -f "$VENV_PYTHON" ]; then
    log "ERROR: Venv not found at $VENV_PYTHON"
    exit 1
  fi

  mkdir -p "$(dirname "$LOG_FILE")"
}

# ── Check for updates ───────────────────────────────────────
check_and_update() {
  cd "$SRC_DIR"

  # Fetch latest
  if ! git fetch origin "$REPO_BRANCH" --quiet 2>/dev/null; then
    log "WARN: git fetch failed (network issue?)"
    return 1
  fi

  local local_hash remote_hash
  local_hash="$(git rev-parse HEAD)"
  remote_hash="$(git rev-parse "origin/$REPO_BRANCH")"

  if [ "$local_hash" = "$remote_hash" ]; then
    # No changes
    return 1
  fi

  # Check if agent code changed
  local agent_changes
  agent_changes="$(git diff --name-only "$local_hash" "$remote_hash" -- apps/agent/ scripts/agent-updater.sh scripts/templates/ 2>/dev/null || echo "")"

  if [ -z "$agent_changes" ]; then
    # Changes exist but not in agent — still pull to stay current
    git reset --hard "origin/$REPO_BRANCH" --quiet
    log "SYNC: Repo updated (no agent changes). $local_hash → $(git rev-parse --short HEAD)"
    return 1
  fi

  log "UPDATE: Agent changes detected ($local_hash → $remote_hash)"
  log "  Changed files:"
  echo "$agent_changes" | while IFS= read -r f; do log "    - $f"; done

  # Pull changes
  git reset --hard "origin/$REPO_BRANCH" --quiet
  local new_hash
  new_hash="$(git rev-parse --short HEAD)"
  log "  Pulled: $new_hash"

  # Reinstall dependencies
  log "  Installing dependencies..."
  if "$VENV_PYTHON" -m pip install -e "$AGENT_SRC" --quiet 2>>"$LOG_FILE"; then
    log "  Dependencies updated."
  else
    log "ERROR: pip install failed!"
    return 1
  fi

  return 0
}

# ── Restart agent ────────────────────────────────────────────
restart_agent() {
  local os_type
  os_type="$(uname -s)"

  case "$os_type" in
    Darwin)
      local uid
      uid="$(id -u)"
      log "  Restarting LaunchAgent..."
      launchctl kickstart -k "gui/$uid/com.rafraf.agent" 2>/dev/null && {
        log "  Agent restarted via kickstart."
        return
      }
      # Fallback: bootout + bootstrap
      launchctl bootout "gui/$uid/com.rafraf.agent" 2>/dev/null || true
      sleep 1
      local plist="$HOME/Library/LaunchAgents/com.rafraf.agent.plist"
      if [ -f "$plist" ]; then
        launchctl bootstrap "gui/$uid" "$plist"
        log "  Agent restarted via bootstrap."
      else
        log "ERROR: Plist not found at $plist"
      fi
      ;;
    Linux)
      log "  Restarting systemd service..."
      sudo systemctl restart rafraf-agent 2>>"$LOG_FILE" && {
        log "  Agent restarted."
      } || {
        log "ERROR: systemctl restart failed"
      }
      ;;
  esac
}

# ── Log rotation (keep last 10000 lines) ────────────────────
rotate_log() {
  if [ -f "$LOG_FILE" ]; then
    local lines
    lines="$(wc -l < "$LOG_FILE")"
    if [ "$lines" -gt 10000 ]; then
      tail -5000 "$LOG_FILE" > "$LOG_FILE.tmp"
      mv "$LOG_FILE.tmp" "$LOG_FILE"
      log "Log rotated ($lines → 5000 lines)"
    fi
  fi
}

# ── Self-update check ───────────────────────────────────────
check_self_update() {
  # If the updater script itself changed, reinstall the updater plist/service
  local os_type
  os_type="$(uname -s)"

  case "$os_type" in
    Darwin)
      local plist_src="$SRC_DIR/scripts/templates/com.rafraf.agent-updater.plist"
      local plist_dst="$HOME/Library/LaunchAgents/com.rafraf.agent-updater.plist"
      if [ -f "$plist_src" ]; then
        local venv_bin="$INSTALL_DIR/venv/bin"
        local rendered
        rendered="$(sed \
          -e "s|{{INSTALL_DIR}}|$INSTALL_DIR|g" \
          -e "s|{{VENV_BIN}}|$venv_bin|g" \
          -e "s|{{HOME}}|$HOME|g" \
          "$plist_src")"
        local rendered_hash current_hash
        rendered_hash="$(echo "$rendered" | md5 -q 2>/dev/null || echo "$rendered" | md5sum | cut -d' ' -f1)"
        current_hash="$(md5 -q "$plist_dst" 2>/dev/null || echo "none")"
        if [ "$rendered_hash" != "$current_hash" ]; then
          # Sadece plist dosyasini guncelle, daemon'u restart ETME
          # (kendini bootout yaparsa bootstrap yapamadan olur)
          # launchd bir sonraki StartInterval'de yeni plist'i okuyacak
          echo "$rendered" > "$plist_dst"
          log "  Updater plist guncellendi (sonraki calistiginda aktif olacak)."
        fi
      fi
      ;;
  esac
}

# ── Main ─────────────────────────────────────────────────────
main() {
  acquire_lock
  preflight
  rotate_log

  if check_and_update; then
    check_self_update
    restart_agent
    log "UPDATE COMPLETE"
  fi
}

main
