# RafRaf Host Agent — Kurulum Rehberi

Tek satir komutla macOS veya Ubuntu uzerine RafRaf Host Agent kurulumu.

## Gereksinimler

| | macOS | Ubuntu |
|---|---|---|
| **OS** | macOS 13+ (Ventura) | Ubuntu 22.04+ |
| **Python** | 3.12+ (yoksa Homebrew ile kurulur) | 3.12+ (yoksa apt ile kurulur) |
| **Git** | Xcode CLT ile gelir | apt ile kurulur |
| **RAM** | 2 GB+ | 2 GB+ |
| **Disk** | 500 MB+ | 500 MB+ |

## Hizli Kurulum

```bash
curl -fsSL https://raw.githubusercontent.com/atknatk/rafraf/develop/scripts/install-agent.sh | bash
```

Script interaktif olarak su bilgileri sorar:

1. **Host ID** — Bu makinenin benzersiz adi (default: hostname)
2. **Backend WebSocket URL** — Backend sunucu adresi
3. **Agent API Key** — Backend'den alinan kimlik dogrulama anahtari
4. **Proje tarama dizinleri** — Git repolarinin taranacagi klasorler

Ardindan opsiyonel bagimliliklari kurmak isteyip istemediginizi sorar:
- Docker
- Playwright (Chromium)
- Maestro CLI
- Xcode build (sadece macOS)
- Node.js

## Unattended Kurulum (CI / Otomasyon)

Environment variable'lari onceden set ederek interaktif soru sormadan kurulum yapilabilir:

```bash
AGENT_HOST_ID=ci-runner \
AGENT_API_KEY=your-api-key-here \
AGENT_BACKEND_WS_URL=wss://api.rafraf.app/ws/agent \
  curl -fsSL https://raw.githubusercontent.com/atknatk/rafraf/develop/scripts/install-agent.sh | bash -s -- --unattended
```

## Kurulum Sonrasi Dizin Yapisi

```
~/.rafraf-agent/
├── src/          # Klonlanmis repo
├── venv/         # Python virtual environment
├── .env          # Agent konfigurasyonu (chmod 600)
└── logs/         # Log dosyalari
```

## Servis Yonetimi

### macOS (LaunchAgent)

```bash
# Durum
launchctl print gui/$(id -u)/com.rafraf.agent

# Durdur
launchctl bootout gui/$(id -u)/com.rafraf.agent

# Baslat
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.rafraf.agent.plist

# Loglari izle
tail -f ~/.rafraf-agent/logs/agent.stdout.log
```

### Ubuntu (systemd)

```bash
# Durum
systemctl status rafraf-agent

# Durdur
sudo systemctl stop rafraf-agent

# Baslat
sudo systemctl start rafraf-agent

# Yeniden baslat
sudo systemctl restart rafraf-agent

# Loglari izle
journalctl -u rafraf-agent -f
```

## Manuel Calistirma (Servis Olmadan)

```bash
source ~/.rafraf-agent/venv/bin/activate
cd ~/.rafraf-agent/src/apps/agent
python -m agent.main
```

## Guncelleme

Scripti tekrar calistirmak mevcut kurulumu gunceller (git pull + pip install):

```bash
curl -fsSL https://raw.githubusercontent.com/atknatk/rafraf/develop/scripts/install-agent.sh | bash
```

Mevcut `.env` dosyaniz korunur (uzerine yazmak isterseniz script sorar).

## Konfigurasyonu Degistirme

`.env` dosyasini duzenleyin ve servisi yeniden baslatin:

```bash
# Duzenle
nano ~/.rafraf-agent/.env

# macOS — yeniden baslat
launchctl bootout gui/$(id -u)/com.rafraf.agent
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.rafraf.agent.plist

# Ubuntu — yeniden baslat
sudo systemctl restart rafraf-agent
```

### .env Degiskenleri

| Degisken | Zorunlu | Aciklama |
|---|---|---|
| `AGENT_HOST_ID` | Evet | Makinenin benzersiz adi |
| `AGENT_API_KEY` | Evet | Backend kimlik dogrulama anahtari |
| `AGENT_BACKEND_WS_URL` | Evet | Backend WebSocket adresi |
| `AGENT_PROJECT_SCAN_PATHS` | Hayir | Taranacak dizinler (JSON array) |
| `AGENT_PROJECT_SCAN_DEPTH` | Hayir | Tarama derinligi (default: 2) |
| `AGENT_PROJECT_SYNC_INTERVAL` | Hayir | Senkronizasyon araligi saniye (default: 300) |
| `AGENT_CAPABILITY_DOCKER` | Hayir | Docker runner (default: false) |
| `AGENT_CAPABILITY_PLAYWRIGHT` | Hayir | Playwright runner (default: false) |
| `AGENT_CAPABILITY_MAESTRO_IOS` | Hayir | Maestro iOS (default: false) |
| `AGENT_CAPABILITY_SHELL` | Hayir | Shell runner (default: true) |
| `AGENT_CAPABILITY_GIT` | Hayir | Git komutlari (default: true) |

## Kaldirma

```bash
bash ~/.rafraf-agent/src/scripts/uninstall-agent.sh
```

Bu komut:
- Servisi durdurur ve devre disi birakir (LaunchAgent / systemd)
- `~/.rafraf-agent/` dizinini tamamen siler

Onay sormadan kaldirmak icin:

```bash
bash ~/.rafraf-agent/src/scripts/uninstall-agent.sh --yes
```

## Sorun Giderme

### Agent baglanamiyor

```bash
# .env'deki WebSocket URL'ini kontrol edin
grep BACKEND_WS_URL ~/.rafraf-agent/.env

# Backend'in calisiyor oldugundan emin olun
curl -s http://localhost:8000/health
```

### Servis baslamiyor (macOS)

```bash
# Hata loglarini kontrol edin
cat ~/.rafraf-agent/logs/agent.stderr.log

# Plist dosyasini dogrulayin
plutil ~/Library/LaunchAgents/com.rafraf.agent.plist
```

### Servis baslamiyor (Ubuntu)

```bash
# Detayli log
journalctl -u rafraf-agent -n 50 --no-pager

# Servis dosyasini dogrulayin
systemd-analyze verify /etc/systemd/system/rafraf-agent.service
```

### Python versiyon hatasi

```bash
# Mevcut Python versiyonunu kontrol edin
python3 --version

# macOS'te Python 3.12 kurun
brew install python@3.12

# Ubuntu'da Python 3.12 kurun
sudo apt install python3.12 python3.12-venv
```
