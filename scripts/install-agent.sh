#!/usr/bin/env bash
set -euo pipefail

# ─────────────────────────────────────────────────────────────
# RafRaf Host Agent — One-Line Installer (macOS + Ubuntu)
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/atknatk/rafraf/develop/scripts/install-agent.sh | bash
#
# Unattended (CI):
#   AGENT_HOST_ID=ci-box AGENT_API_KEY=xxx AGENT_BACKEND_WS_URL=wss://... \
#     curl -fsSL .../install-agent.sh | bash -s -- --unattended
# ─────────────────────────────────────────────────────────────

REPO_URL="https://github.com/atknatk/rafraf.git"
REPO_BRANCH="develop"
MIN_PYTHON="3.12"

# ── Colors ───────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'

info()    { echo -e "${BLUE}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERR]${NC}   $*"; exit 1; }

# ── Parse flags ──────────────────────────────────────────────
UNATTENDED=false
for arg in "$@"; do
  case "$arg" in
    --unattended) UNATTENDED=true ;;
  esac
done

ask() {
  # ask "prompt" "default" → sets REPLY
  local prompt="$1" default="${2:-}"
  if [ "$UNATTENDED" = true ]; then
    REPLY="$default"
    return
  fi
  if [ -n "$default" ]; then
    read -rp "$(echo -e "${BOLD}$prompt${NC} [$default]: ")" REPLY
    REPLY="${REPLY:-$default}"
  else
    read -rp "$(echo -e "${BOLD}$prompt${NC}: ")" REPLY
  fi
}

ask_yn() {
  # ask_yn "prompt" "y/n default" → return 0 (yes) or 1 (no)
  local prompt="$1" default="${2:-n}"
  if [ "$UNATTENDED" = true ]; then
    [[ "$default" =~ ^[Yy] ]] && return 0 || return 1
  fi
  local yn_hint="y/N"
  [[ "$default" =~ ^[Yy] ]] && yn_hint="Y/n"
  read -rp "$(echo -e "${BOLD}$prompt${NC} [$yn_hint]: ")" ans
  ans="${ans:-$default}"
  [[ "$ans" =~ ^[Yy] ]] && return 0 || return 1
}

# ── Detect OS ────────────────────────────────────────────────
detect_os() {
  case "$(uname -s)" in
    Darwin) OS="macos" ;;
    Linux)
      if [ -f /etc/os-release ]; then
        . /etc/os-release
        case "$ID" in
          ubuntu|debian) OS="ubuntu" ;;
          *) OS="linux-$ID" ;;
        esac
      else
        OS="linux-unknown"
      fi
      ;;
    *) error "Desteklenmeyen platform: $(uname -s). Sadece macOS ve Ubuntu destekleniyor." ;;
  esac
  info "Platform: $OS ($(uname -m))"
}

# ── Set install paths ────────────────────────────────────────
set_paths() {
  INSTALL_DIR="$HOME/.rafraf-agent"
  AGENT_SRC="$INSTALL_DIR/src/apps/agent"
  VENV_DIR="$INSTALL_DIR/venv"
  VENV_PYTHON="$VENV_DIR/bin/python"
  VENV_BIN="$VENV_DIR/bin"
  ENV_FILE="$INSTALL_DIR/.env"
  LOG_DIR="$INSTALL_DIR/logs"
}

# ── Python check / install ───────────────────────────────────
version_gte() {
  # Returns 0 if $1 >= $2
  printf '%s\n%s' "$2" "$1" | sort -V -C
}

ensure_python() {
  local py_cmd=""

  # Try python3.12 first, then python3
  for cmd in python3.12 python3; do
    if command -v "$cmd" &>/dev/null; then
      local ver
      ver="$("$cmd" --version 2>&1 | grep -oE '[0-9]+\.[0-9]+')"
      if version_gte "$ver" "$MIN_PYTHON"; then
        py_cmd="$cmd"
        break
      fi
    fi
  done

  if [ -z "$py_cmd" ]; then
    warn "Python $MIN_PYTHON+ bulunamadi."
    if [ "$OS" = "macos" ]; then
      info "Homebrew ile Python $MIN_PYTHON kurulacak..."
      if ! command -v brew &>/dev/null; then
        error "Homebrew bulunamadi. Oncelikle https://brew.sh adresinden Homebrew kurun."
      fi
      brew install python@3.12
      py_cmd="python3.12"
    else
      info "apt ile Python $MIN_PYTHON kurulacak..."
      sudo apt-get update -qq
      sudo apt-get install -y -qq python3.12 python3.12-venv python3-pip
      py_cmd="python3.12"
    fi
  fi

  PYTHON_CMD="$py_cmd"
  success "Python: $($PYTHON_CMD --version)"
}

# ── Git check ────────────────────────────────────────────────
ensure_git() {
  if command -v git &>/dev/null; then
    success "Git: $(git --version | head -1)"
    return
  fi

  warn "Git bulunamadi."
  if [ "$OS" = "macos" ]; then
    info "Xcode CLT ile git kurulacak..."
    xcode-select --install 2>/dev/null || true
    error "Git kurulduktan sonra scripti tekrar calistirin."
  else
    info "apt ile git kurulacak..."
    sudo apt-get update -qq
    sudo apt-get install -y -qq git
    success "Git kuruldu."
  fi
}

# ── Clone / Update repo ─────────────────────────────────────
setup_repo() {
  local src_root="$INSTALL_DIR/src"

  if [ -d "$src_root/.git" ]; then
    info "Mevcut repo guncelleniyor..."
    git -C "$src_root" fetch origin "$REPO_BRANCH" --quiet
    git -C "$src_root" reset --hard "origin/$REPO_BRANCH" --quiet
    success "Repo guncellendi ($(git -C "$src_root" rev-parse --short HEAD))"
  else
    info "Repo clone ediliyor..."
    mkdir -p "$INSTALL_DIR"
    git clone --branch "$REPO_BRANCH" --depth 1 --quiet "$REPO_URL" "$src_root"
    success "Repo clone edildi."
  fi
}

# ── Python venv + deps ───────────────────────────────────────
setup_venv() {
  if [ ! -d "$VENV_DIR" ]; then
    info "Virtual environment olusturuluyor..."
    "$PYTHON_CMD" -m venv "$VENV_DIR"
  fi

  info "Bagimliliklar yukleniyor..."
  "$VENV_PYTHON" -m pip install --upgrade pip --quiet
  "$VENV_PYTHON" -m pip install -e "$AGENT_SRC" --quiet
  success "Python bagimliliklari yuklendi."
}

# ── Interactive configuration ────────────────────────────────
configure_env() {
  mkdir -p "$LOG_DIR"

  if [ -f "$ENV_FILE" ] && ! ask_yn "Mevcut .env dosyasi bulundu. Uzerine yazilsin mi?" "n"; then
    success "Mevcut .env korunuyor."
    return
  fi

  local default_host_id
  default_host_id="$(hostname -s | tr '[:upper:]' '[:lower:]' | tr ' ' '-')"

  local default_scan_paths
  if [ "$OS" = "macos" ]; then
    default_scan_paths="[\"$HOME/Documents/GitHub\", \"$HOME/Projects\"]"
  else
    default_scan_paths="[\"$HOME/projects\", \"$HOME/code\"]"
  fi

  echo ""
  info "─── Agent Konfigurasyonu ───"
  echo ""

  ask "Host ID (bu makinenin benzersiz adi)" "${AGENT_HOST_ID:-$default_host_id}"
  local host_id="$REPLY"

  ask "Backend WebSocket URL" "${AGENT_BACKEND_WS_URL:-ws://localhost:8000/ws/agent}"
  local ws_url="$REPLY"

  ask "Agent API Key (backend'den alinir)" "${AGENT_API_KEY:-}"
  local api_key="$REPLY"
  if [ -z "$api_key" ]; then
    error "AGENT_API_KEY bos birakilamaz."
  fi

  ask "Proje tarama dizinleri (JSON array)" "$default_scan_paths"
  local scan_paths="$REPLY"

  cat > "$ENV_FILE" <<EOF
# RafRaf Agent Configuration
# Generated: $(date -u +"%Y-%m-%dT%H:%M:%SZ")

AGENT_HOST_ID=$host_id
AGENT_API_KEY=$api_key
AGENT_BACKEND_WS_URL=$ws_url
AGENT_PROJECT_SCAN_PATHS=$scan_paths
AGENT_PROJECT_SCAN_DEPTH=2
AGENT_PROJECT_SYNC_INTERVAL=300

# Capabilities (true/false)
AGENT_CAPABILITY_SHELL=true
AGENT_CAPABILITY_GIT=true
AGENT_CAPABILITY_PYTHON=true
AGENT_CAPABILITY_DOCKER=false
AGENT_CAPABILITY_PLAYWRIGHT=false
AGENT_CAPABILITY_MAESTRO_IOS=false
AGENT_CAPABILITY_MAESTRO_ANDROID=false
AGENT_CAPABILITY_NODEJS=false
AGENT_CAPABILITY_XCODE_BUILD=false
AGENT_CAPABILITY_ANDROID_BUILD=false
EOF

  chmod 600 "$ENV_FILE"
  success ".env olusturuldu: $ENV_FILE"
}

# ── Optional dependencies ────────────────────────────────────
install_optional_deps() {
  echo ""
  info "─── Opsiyonel Bagimliliklar ───"
  echo ""

  # Docker
  if command -v docker &>/dev/null; then
    success "Docker mevcut: $(docker --version | head -1)"
    sed -i.bak 's/AGENT_CAPABILITY_DOCKER=false/AGENT_CAPABILITY_DOCKER=true/' "$ENV_FILE" && rm -f "$ENV_FILE.bak"
  else
    if ask_yn "Docker kurulsun mu?" "n"; then
      if [ "$OS" = "macos" ]; then
        warn "Docker Desktop'i https://docker.com/products/docker-desktop adresinden indirin."
      else
        info "Docker kurulumu baslatiliyor..."
        curl -fsSL https://get.docker.com | sh
        sudo usermod -aG docker "$USER" 2>/dev/null || true
        success "Docker kuruldu. Yeni oturum acarak grup degisikligi aktif olacak."
      fi
    fi
  fi

  # Playwright
  if ask_yn "Playwright (Chromium) kurulsun mu? (web screenshot/test)" "n"; then
    info "Playwright Chromium yukleniyor..."
    "$VENV_PYTHON" -m playwright install chromium
    if [ "$OS" != "macos" ]; then
      "$VENV_PYTHON" -m playwright install-deps chromium 2>/dev/null || true
    fi
    sed -i.bak 's/AGENT_CAPABILITY_PLAYWRIGHT=false/AGENT_CAPABILITY_PLAYWRIGHT=true/' "$ENV_FILE" && rm -f "$ENV_FILE.bak"
    success "Playwright Chromium yuklendi."
  fi

  # Maestro
  if ask_yn "Maestro CLI kurulsun mu? (mobile test)" "n"; then
    info "Maestro CLI yukleniyor..."
    curl -Ls "https://get.maestro.mobile.dev" | bash
    if [ "$OS" = "macos" ]; then
      sed -i.bak 's/AGENT_CAPABILITY_MAESTRO_IOS=false/AGENT_CAPABILITY_MAESTRO_IOS=true/' "$ENV_FILE" && rm -f "$ENV_FILE.bak"
    fi
    sed -i.bak 's/AGENT_CAPABILITY_MAESTRO_ANDROID=false/AGENT_CAPABILITY_MAESTRO_ANDROID=true/' "$ENV_FILE" && rm -f "$ENV_FILE.bak"
    success "Maestro CLI yuklendi."
  fi

  # Xcode (macOS only)
  if [ "$OS" = "macos" ]; then
    if command -v xcodebuild &>/dev/null; then
      if ask_yn "Xcode build capability aktif edilsin mi?" "n"; then
        sed -i.bak 's/AGENT_CAPABILITY_XCODE_BUILD=false/AGENT_CAPABILITY_XCODE_BUILD=true/' "$ENV_FILE" && rm -f "$ENV_FILE.bak"
        success "Xcode build capability aktif."
      fi
    fi
  fi

  # Node.js
  if command -v node &>/dev/null; then
    if ask_yn "Node.js capability aktif edilsin mi? ($(node --version))" "n"; then
      sed -i.bak 's/AGENT_CAPABILITY_NODEJS=false/AGENT_CAPABILITY_NODEJS=true/' "$ENV_FILE" && rm -f "$ENV_FILE.bak"
      success "Node.js capability aktif."
    fi
  fi
}

# ── Service setup ────────────────────────────────────────────
setup_service_macos() {
  local uid
  uid="$(id -u)"

  # ── Agent daemon ──
  local plist_src="$INSTALL_DIR/src/scripts/templates/com.rafraf.agent.plist"
  local plist_dst="$HOME/Library/LaunchAgents/com.rafraf.agent.plist"

  if [ ! -f "$plist_src" ]; then
    error "Plist template bulunamadi: $plist_src"
  fi

  launchctl bootout "gui/$uid/com.rafraf.agent" 2>/dev/null || true

  sed \
    -e "s|{{VENV_PYTHON}}|$VENV_PYTHON|g" \
    -e "s|{{VENV_BIN}}|$VENV_BIN|g" \
    -e "s|{{AGENT_SRC}}|$AGENT_SRC|g" \
    -e "s|{{LOG_DIR}}|$LOG_DIR|g" \
    "$plist_src" > "$plist_dst"

  launchctl bootstrap "gui/$uid" "$plist_dst"
  success "Agent LaunchAgent kuruldu ve baslatildi."

  # ── Auto-updater daemon ──
  local updater_plist_src="$INSTALL_DIR/src/scripts/templates/com.rafraf.agent-updater.plist"
  local updater_plist_dst="$HOME/Library/LaunchAgents/com.rafraf.agent-updater.plist"

  if [ -f "$updater_plist_src" ]; then
    launchctl bootout "gui/$uid/com.rafraf.agent-updater" 2>/dev/null || true

    sed \
      -e "s|{{INSTALL_DIR}}|$INSTALL_DIR|g" \
      -e "s|{{VENV_BIN}}|$VENV_BIN|g" \
      -e "s|{{HOME}}|$HOME|g" \
      "$updater_plist_src" > "$updater_plist_dst"

    launchctl bootstrap "gui/$uid" "$updater_plist_dst"
    success "Auto-updater kuruldu (5 dk aralikla kontrol eder)."
  else
    warn "Updater plist template bulunamadi, auto-update devre disi."
  fi
}

setup_service_ubuntu() {
  # ── Agent service ──
  local svc_src="$INSTALL_DIR/src/scripts/templates/rafraf-agent.service"
  local svc_dst="/etc/systemd/system/rafraf-agent.service"

  if [ ! -f "$svc_src" ]; then
    error "Systemd template bulunamadi: $svc_src"
  fi

  local tmp_svc
  tmp_svc="$(mktemp)"
  sed \
    -e "s|{{SERVICE_USER}}|$USER|g" \
    -e "s|{{VENV_PYTHON}}|$VENV_PYTHON|g" \
    -e "s|{{AGENT_SRC}}|$AGENT_SRC|g" \
    -e "s|{{ENV_FILE}}|$ENV_FILE|g" \
    -e "s|{{INSTALL_DIR}}|$INSTALL_DIR|g" \
    "$svc_src" > "$tmp_svc"

  sudo cp "$tmp_svc" "$svc_dst"
  rm -f "$tmp_svc"

  sudo systemctl daemon-reload
  sudo systemctl enable rafraf-agent
  sudo systemctl restart rafraf-agent
  success "Agent systemd servisi kuruldu ve baslatildi."

  # ── Auto-updater service + timer ──
  local updater_svc_src="$INSTALL_DIR/src/scripts/templates/rafraf-agent-updater.service"
  local updater_timer_src="$INSTALL_DIR/src/scripts/templates/rafraf-agent-updater.timer"

  if [ -f "$updater_svc_src" ] && [ -f "$updater_timer_src" ]; then
    local tmp_updater_svc
    tmp_updater_svc="$(mktemp)"
    sed \
      -e "s|{{SERVICE_USER}}|$USER|g" \
      -e "s|{{INSTALL_DIR}}|$INSTALL_DIR|g" \
      "$updater_svc_src" > "$tmp_updater_svc"

    sudo cp "$tmp_updater_svc" /etc/systemd/system/rafraf-agent-updater.service
    sudo cp "$updater_timer_src" /etc/systemd/system/rafraf-agent-updater.timer
    rm -f "$tmp_updater_svc"

    sudo systemctl daemon-reload
    sudo systemctl enable rafraf-agent-updater.timer
    sudo systemctl start rafraf-agent-updater.timer
    success "Auto-updater kuruldu (5 dk aralikla kontrol eder)."
  else
    warn "Updater template bulunamadi, auto-update devre disi."
  fi
}

# ── Summary ──────────────────────────────────────────────────
print_summary() {
  echo ""
  echo -e "${GREEN}${BOLD}════════════════════════════════════════════${NC}"
  echo -e "${GREEN}${BOLD}  RafRaf Agent kurulumu tamamlandi!${NC}"
  echo -e "${GREEN}${BOLD}════════════════════════════════════════════${NC}"
  echo ""
  echo -e "  Dizin:    ${BOLD}$INSTALL_DIR${NC}"
  echo -e "  .env:     ${BOLD}$ENV_FILE${NC}"
  echo -e "  Loglar:   ${BOLD}$LOG_DIR${NC}"
  echo ""

  if [ "$OS" = "macos" ]; then
    echo -e "  ${BOLD}Faydali komutlar:${NC}"
    echo "    Durum:      launchctl print gui/$(id -u)/com.rafraf.agent"
    echo "    Durdur:     launchctl bootout gui/$(id -u)/com.rafraf.agent"
    echo "    Baslat:     launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.rafraf.agent.plist"
    echo "    Agent log:  tail -f $LOG_DIR/agent.stdout.log"
    echo "    Update log: tail -f $LOG_DIR/updater.log"
  else
    echo -e "  ${BOLD}Faydali komutlar:${NC}"
    echo "    Durum:      systemctl status rafraf-agent"
    echo "    Durdur:     sudo systemctl stop rafraf-agent"
    echo "    Baslat:     sudo systemctl start rafraf-agent"
    echo "    Agent log:  journalctl -u rafraf-agent -f"
    echo "    Update log: tail -f $LOG_DIR/updater.log"
  fi

  echo ""
  echo -e "  ${BOLD}Auto-update:${NC} Her 5 dakikada kontrol eder, degisiklik varsa otomatik gunceller."
  echo -e "  Kaldirmak icin: ${BOLD}bash $INSTALL_DIR/src/scripts/uninstall-agent.sh${NC}"
  echo ""
}

# ── Main ─────────────────────────────────────────────────────
main() {
  echo ""
  echo -e "${BOLD}╔══════════════════════════════════════╗${NC}"
  echo -e "${BOLD}║   RafRaf Host Agent Installer v1.0   ║${NC}"
  echo -e "${BOLD}╚══════════════════════════════════════╝${NC}"
  echo ""

  detect_os
  set_paths
  ensure_git
  ensure_python
  setup_repo
  setup_venv
  configure_env
  install_optional_deps

  echo ""
  if [ "$OS" = "macos" ]; then
    if ask_yn "Agent'i LaunchAgent olarak servis kurup baslatilsin mi?" "y"; then
      setup_service_macos
    else
      info "Servisi kendiniz baslatabilirsiniz:"
      echo "  source $VENV_DIR/bin/activate && cd $AGENT_SRC && python -m agent.main"
    fi
  else
    if ask_yn "Agent'i systemd servisi olarak kurup baslatilsin mi?" "y"; then
      setup_service_ubuntu
    else
      info "Servisi kendiniz baslatabilirsiniz:"
      echo "  source $VENV_DIR/bin/activate && cd $AGENT_SRC && python -m agent.main"
    fi
  fi

  print_summary
}

main "$@"
