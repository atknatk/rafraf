#!/usr/bin/env bash
set -euo pipefail

# ─────────────────────────────────────────────────────────────
# RafRaf Host Agent — Uninstaller (macOS + Ubuntu)
# ─────────────────────────────────────────────────────────────

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'

info()    { echo -e "${BLUE}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }

INSTALL_DIR="$HOME/.rafraf-agent"

echo ""
echo -e "${BOLD}RafRaf Host Agent — Uninstaller${NC}"
echo ""

# ── Confirm ──────────────────────────────────────────────────
if [[ "${1:-}" != "--yes" ]]; then
  read -rp "$(echo -e "${YELLOW}Agent tamamen kaldirilacak. Devam edilsin mi? [y/N]:${NC} ")" ans
  [[ "$ans" =~ ^[Yy] ]] || { info "Iptal edildi."; exit 0; }
fi

# ── Stop & remove service ────────────────────────────────────
case "$(uname -s)" in
  Darwin)
    plist="$HOME/Library/LaunchAgents/com.rafraf.agent.plist"
    if [ -f "$plist" ]; then
      launchctl bootout "gui/$(id -u)/com.rafraf.agent" 2>/dev/null || true
      rm -f "$plist"
      success "LaunchAgent durduruldu ve kaldirildi."
    else
      info "LaunchAgent bulunamadi, atlanıyor."
    fi
    ;;
  Linux)
    if systemctl is-active --quiet rafraf-agent 2>/dev/null; then
      sudo systemctl stop rafraf-agent
      sudo systemctl disable rafraf-agent
      success "Systemd servisi durduruldu."
    fi
    svc="/etc/systemd/system/rafraf-agent.service"
    if [ -f "$svc" ]; then
      sudo rm -f "$svc"
      sudo systemctl daemon-reload
      success "Systemd servisi kaldirildi."
    else
      info "Systemd servisi bulunamadi, atlaniyor."
    fi
    ;;
esac

# ── Remove install directory ─────────────────────────────────
if [ -d "$INSTALL_DIR" ]; then
  rm -rf "$INSTALL_DIR"
  success "Kurulum dizini kaldirildi: $INSTALL_DIR"
else
  info "Kurulum dizini bulunamadi: $INSTALL_DIR"
fi

echo ""
success "RafRaf Agent tamamen kaldirildi."
echo ""
