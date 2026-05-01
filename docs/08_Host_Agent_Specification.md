# RafRaf — Host Agent Specification

> **⚠️ ARCHIVED — V2'ye ertelendi.** Bu doc RafRaf'ın v0.1 vizyonuna ait;
> V1'de scope dışı (bkz. [`10_Production_Pivot_Spec.md`](10_Production_Pivot_Spec.md) §5).
> V2'de güncellenecek.

**Document 8/8** | Version 1.0 | March 2026

---

## 1. Genel Bakis

Host Agent, fiziksel makinelerde (Mac veya Ubuntu) calisan hafif bir daemon servisidir. Backend'e (AWS EKS) WebSocket uzerinden baglanir, backend'ten gelen komutlari yerel olarak calistirir ve sonuclari geri gonderir. Sistem 3 host agent'tan olusur.

### 1.1 Host Envanteri

| Host ID | Makine | OS | Ozel Yetenek | 7/24 | Projeler |
|---------|--------|----|-------------|------|----------|
| macbook-pro | MacBook Pro (Yeni) | macOS 15+ | Xcode 16+, iOS Simulator, Maestro iOS, Swift | Hayir | iOS projeleri + genel |
| macbook-air | MacBook Air (Eski) | macOS 14 | Android SDK, Android Emulator, Maestro Android | Hayir | Android projeleri + genel |
| ubuntu-dev | Ubuntu Dev Server | Ubuntu 22.04 LTS | Node.js 20+, Next.js, yuksek kaynak, 7/24 | Evet | Node.js / Next.js web projeleri |

### 1.2 Yetenek Matrisi

| Yetenek | macbook-pro | macbook-air | ubuntu-dev |
|---------|-------------|-------------|------------|
| Docker | ✅ | ✅ | ✅ |
| Playwright (Chrome) | ✅ | ✅ | ✅ (headless) |
| Maestro iOS | ✅ | ❌ | ❌ |
| Maestro Android | ❌ | ✅ | ❌ |
| Shell | ✅ | ✅ | ✅ |
| Xcode Build | ✅ | ❌ | ❌ |
| Android Build | ❌ | ✅ | ❌ |
| Node.js / npm | ✅ | ✅ | ✅ |
| Python | ✅ | ✅ | ✅ |
| Git | ✅ | ✅ | ✅ |

---

## 2. Agent Mimarisi

### 2.1 Bilesenler

```
┌─────────────────────────────────────────────────┐
│                 Host Agent                       │
│                                                  │
│  ┌───────────────────────────────────────────┐   │
│  │  Connection Manager                        │   │
│  │  • WSS baglanti (backend'e)               │   │
│  │  • Auth (API key)                          │   │
│  │  • Heartbeat (30sn)                        │   │
│  │  • Auto-reconnect (exponential backoff)    │   │
│  └───────────────────┬───────────────────────┘   │
│                      │                           │
│  ┌───────────────────▼───────────────────────┐   │
│  │  Command Executor                          │   │
│  │  • Komut alma ve calistirma               │   │
│  │  • Timeout yonetimi                        │   │
│  │  • Sonuc dondurme                          │   │
│  │  • Ilerleme bildirimi (uzun islemler)      │   │
│  └───────────────────┬───────────────────────┘   │
│                      │                           │
│  ┌──────────┐ ┌──────┴─────┐ ┌───────────────┐  │
│  │ Docker   │ │ Playwright │ │ Maestro       │  │
│  │ Runner   │ │ Runner     │ │ Runner        │  │
│  └──────────┘ └────────────┘ └───────────────┘  │
│  ┌──────────┐ ┌────────────┐ ┌───────────────┐  │
│  │ Shell    │ │ S3 Upload  │ │ Resource      │  │
│  │ Runner   │ │ Manager    │ │ Monitor       │  │
│  └──────────┘ └────────────┘ └───────────────┘  │
│                                                  │
└─────────────────────────────────────────────────┘
```

### 2.2 Proje Dizin Yapisi

```
rafraf-agent/
├── agent/
│   ├── __init__.py
│   ├── main.py                    # Entry point, daemon baslat
│   ├── config.py                  # Agent konfigurasyonu
│   │
│   ├── connection/
│   │   ├── __init__.py
│   │   ├── websocket_client.py    # WSS baglanti yonetimi
│   │   ├── auth.py                # API key dogrulama
│   │   └── heartbeat.py           # Periyodik saglik raporu
│   │
│   ├── executor/
│   │   ├── __init__.py
│   │   ├── command_handler.py     # Gelen komutlari yonlendirme
│   │   ├── docker_runner.py       # Docker islemleri
│   │   ├── playwright_runner.py   # Playwright islemleri
│   │   ├── maestro_runner.py      # Maestro islemleri
│   │   ├── shell_runner.py        # Shell komutlari
│   │   └── security.py            # Komut whitelist/blacklist
│   │
│   ├── upload/
│   │   ├── __init__.py
│   │   └── s3_uploader.py         # Screenshot/log S3 upload
│   │
│   └── monitor/
│       ├── __init__.py
│       └── resource_monitor.py    # CPU, RAM, disk izleme
│
├── config/
│   ├── agent.yaml                 # Agent konfigurasyonu
│   └── projects.yaml              # Lokal proje yollari
│
├── scripts/
│   ├── install_mac.sh             # macOS kurulum scripti
│   ├── install_ubuntu.sh          # Ubuntu kurulum scripti
│   ├── start.sh                   # Agent baslat
│   ├── stop.sh                    # Agent durdur
│   └── status.sh                  # Agent durumu
│
├── systemd/
│   └── rafraf-agent.service  # Ubuntu systemd service
│
├── launchd/
│   └── com.rafraf.agent.plist  # macOS launchd service
│
├── requirements.txt
├── pyproject.toml
└── README.md
```

---

## 3. Konfigürasyon

### 3.1 Agent Konfigurasyonu (agent.yaml)

```yaml
# agent.yaml — Her host icin farkli

agent:
  host_id: "macbook-pro"              # Benzersiz host kimlik
  api_key: "agent-key-xxx"            # Backend auth icin
  backend_url: "wss://api.supervisor.example.com/ws/agent"

connection:
  heartbeat_interval: 30               # Saniye
  reconnect_max_delay: 30              # Saniye
  reconnect_initial_delay: 1           # Saniye
  command_timeout_default: 120         # Saniye

capabilities:
  docker: true
  playwright: true
  maestro_ios: true                     # Sadece macbook-pro'da true
  maestro_android: false
  shell: true
  xcode_build: true                     # Sadece macbook-pro'da true

paths:
  screenshots_dir: "/tmp/rafraf/screenshots"
  logs_dir: "/tmp/rafraf/logs"
  playwright_cache: "/tmp/rafraf/playwright"

s3:
  bucket: "rafraf-files"
  region: "eu-west-1"
  # AWS credentials: ortam degiskenlerinden veya IAM role'den alinir

security:
  # Komut calistirma kisitlamalari
  max_concurrent_commands: 3
  shell_whitelist_enabled: true
  shell_blacklist_enabled: true

resource_monitoring:
  enabled: true
  interval: 30                         # Saniye
  disk_warning_threshold_percent: 85
  memory_warning_threshold_percent: 90
```

### 3.2 macbook-air icin Farklar

```yaml
agent:
  host_id: "macbook-air"

capabilities:
  maestro_ios: false
  maestro_android: true
  xcode_build: false
  android_build: true
```

### 3.3 ubuntu-dev icin Farklar

```yaml
agent:
  host_id: "ubuntu-dev"

capabilities:
  maestro_ios: false
  maestro_android: false
  xcode_build: false
  android_build: false
  # Node.js / Next.js projeleri icin optimize

paths:
  projects_base: "/home/atakan/projects"
```

### 3.4 Proje Yollari (projects.yaml)

Her host kendi proje yollarini bilir:

**macbook-pro:**
```yaml
projects:
  - slug: project-x
    path: "/Users/atakan/projects/project-x"
    docker_compose: "docker-compose.yml"
  - slug: project-z
    path: "/Users/atakan/projects/project-z"
    docker_compose: "docker-compose.dev.yml"
```

**ubuntu-dev:**
```yaml
projects:
  - slug: project-z
    path: "/home/atakan/projects/project-z"
    docker_compose: "docker-compose.yml"
  - slug: project-w
    path: "/home/atakan/projects/project-w"
    docker_compose: "docker-compose.yml"
```

---

## 4. Baglanti Yonetimi

### 4.1 Baglanti Yasam Dongusu

```
Agent Basladi
    │
    ▼
API Key ile WSS Baglantisi Ac
    │
    ├── Basarili → agent_register mesaji gonder → Heartbeat basla → Komut bekle
    │
    ├── Auth Hatasi → Log yaz, 60 saniye bekle, tekrar dene
    │
    └── Baglanti Koptu → Exponential backoff ile reconnect
        (1s → 2s → 4s → 8s → 16s → max 30s)
        Basarili olunca → agent_register tekrar gonder → Komut bekle
```

### 4.2 Reconnect Stratejisi

```python
class ConnectionManager:
    def __init__(self):
        self.reconnect_delay = 1.0
        self.max_delay = 30.0
        self.is_connected = False

    async def connect(self):
        while True:
            try:
                self.ws = await websockets.connect(
                    self.config.backend_url,
                    extra_headers={"X-API-Key": self.config.api_key}
                )
                self.is_connected = True
                self.reconnect_delay = 1.0  # Reset
                await self.register()
                await self.listen()
            except ConnectionClosed:
                self.is_connected = False
                await asyncio.sleep(self.reconnect_delay)
                self.reconnect_delay = min(
                    self.reconnect_delay * 2,
                    self.max_delay
                )
```

### 4.3 Heartbeat

```python
async def send_heartbeat(self):
    while self.is_connected:
        await self.ws.send(json.dumps({
            "type": "agent_heartbeat",
            "host_id": self.config.host_id,
            "content": {
                "status": "online",
                "uptime_seconds": self.get_uptime(),
                "active_tasks": len(self.active_commands),
                "resources": self.resource_monitor.get_current(),
                "docker_running_containers": self.docker_runner.count_running()
            }
        }))
        await asyncio.sleep(self.config.heartbeat_interval)
```

---

## 5. Komut Calistirma

### 5.1 Komut Alma ve Yonlendirme

```python
async def handle_command(self, message: dict):
    command_id = message["command_id"]
    tool = message["content"]["tool"]
    action = message["content"]["action"]
    params = message["content"]["params"]
    timeout = message["content"].get("timeout_seconds", 120)

    # Guvenlik kontrolu
    if not self.security.is_allowed(tool, action, params):
        await self.send_result(command_id, success=False,
            error="Bu komut guvenlik politikasi tarafindan engellendi")
        return

    # Yetenek kontrolu
    if tool == "mobile_tester_ios" and not self.config.capabilities.maestro_ios:
        await self.send_result(command_id, success=False,
            error="Bu host'ta iOS testi desteklenmiyor")
        return

    # Komutu calistir
    try:
        runner = self.get_runner(tool)
        result = await asyncio.wait_for(
            runner.execute(action, params),
            timeout=timeout
        )
        await self.send_result(command_id, success=True, result=result)
    except asyncio.TimeoutError:
        await self.send_result(command_id, success=False,
            error=f"Komut {timeout} saniye icinde tamamlanamadi")
    except Exception as e:
        await self.send_result(command_id, success=False, error=str(e))
```

### 5.2 Docker Runner

```python
class DockerRunner:
    def __init__(self, projects_config):
        self.docker_client = docker.from_env()
        self.projects = projects_config

    async def execute(self, action: str, params: dict) -> dict:
        project = self.projects[params["project_slug"]]
        project_path = project["path"]

        if action == "compose_up":
            return await self._compose_up(project_path, project["docker_compose"])
        elif action == "compose_down":
            return await self._compose_down(project_path, project["docker_compose"])
        elif action == "compose_logs":
            return await self._compose_logs(project_path, params.get("service"),
                                            params.get("tail", 100))
        elif action == "health_check":
            return await self._health_check(project_path, project["docker_compose"])
        # ... diger aksiyonlar

    async def _compose_up(self, path, compose_file):
        proc = await asyncio.create_subprocess_exec(
            "docker", "compose", "-f", compose_file, "up", "-d",
            cwd=path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        return {
            "success": proc.returncode == 0,
            "output": stdout.decode(),
            "error": stderr.decode() if proc.returncode != 0 else None
        }
```

### 5.3 Playwright Runner

```python
class PlaywrightRunner:
    async def execute(self, action: str, params: dict) -> dict:
        if action == "take_screenshot":
            return await self._screenshot(params)
        elif action == "run_test_suite":
            return await self._run_tests(params)
        elif action == "check_page_load":
            return await self._check_page(params)
        # ... diger aksiyonlar

    async def _screenshot(self, params):
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": 1920, "height": 1080})
            await page.goto(params["url"], wait_until="networkidle")

            screenshot_bytes = await page.screenshot(full_page=params.get("full_page", False))
            await browser.close()

        # S3'e yukle
        s3_url = await self.s3_uploader.upload(
            screenshot_bytes,
            f"screenshots/{params['project_slug']}/{int(time.time())}.png"
        )

        return {
            "success": True,
            "screenshot_url": s3_url,
            "page_title": await page.title()
        }
```

### 5.4 Maestro Runner

```python
class MaestroRunner:
    async def execute(self, action: str, params: dict) -> dict:
        if action == "run_flow":
            return await self._run_flow(params)
        elif action == "take_screenshot":
            return await self._screenshot(params)
        elif action == "run_all_flows":
            return await self._run_all(params)

    async def _run_flow(self, params):
        platform = params["platform"]  # "ios" veya "android"
        flow_file = params["flow_file"]

        cmd = ["maestro", "test", flow_file]
        if platform == "ios":
            cmd.extend(["--device", self.config.ios_device])

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=params.get("cwd")
        )
        stdout, stderr = await proc.communicate()

        # Screenshot'lari topla ve S3'e yukle
        screenshots = await self._upload_screenshots(params["project_slug"])

        return {
            "success": proc.returncode == 0,
            "output": stdout.decode(),
            "screenshots": screenshots
        }
```

### 5.5 Shell Runner (Guvenlikli)

```python
class ShellRunner:
    WHITELIST = [
        r"^git\s+(status|log|diff|branch|show|remote|tag)",
        r"^ls\b", r"^cat\b", r"^head\b", r"^tail\b", r"^grep\b", r"^find\b", r"^wc\b",
        r"^docker\s+(ps|logs|stats|inspect|images)",
        r"^npm\s+(test|run\s+lint|run\s+build|run\s+dev|list)",
        r"^npx\b",
        r"^python\s+-m\s+(pytest|pylint|black|mypy)",
        r"^node\b",
        r"^curl\s+.*--request\s+GET|^curl\s+-s",
        r"^df\b", r"^du\b", r"^free\b", r"^top\s+-bn1", r"^ps\b",
        r"^which\b", r"^whoami\b", r"^uname\b", r"^hostname\b",
    ]

    BLACKLIST = [
        r"rm\s+-rf\s+/",
        r"mkfs\b",
        r"dd\s+if=/dev",
        r":\(\)\s*\{",              # Fork bomb
        r">\s*/dev/sd",
        r"shutdown\b", r"reboot\b", r"halt\b",
        r"passwd\b",
        r"sudo\s+rm",
    ]

    APPROVAL_REQUIRED = [
        r"^kubectl\b",
        r"^aws\b",
        r"^docker\s+push",
        r"^git\s+push",
        r"^npm\s+publish",
        r"^rm\b",
        r"^chmod\b", r"^chown\b",
        r"^pip\s+install",
        r"^sudo\b",
    ]

    async def execute(self, action: str, params: dict) -> dict:
        command = params["command"]
        cwd = params.get("cwd")
        timeout = params.get("timeout", 60)

        # Blacklist kontrolu — ASLA calistirma
        if self._matches_any(command, self.BLACKLIST):
            return {"success": False, "error": "YASAKLI KOMUT: Bu komut calistirilamaz."}

        # Approval kontrolu — backend'e sor
        if self._matches_any(command, self.APPROVAL_REQUIRED):
            return {"success": False, "error": "ONAY_GEREKLI", "command": command}

        # Whitelist kontrolu
        if not self._matches_any(command, self.WHITELIST):
            return {"success": False, "error": "TANIMLANMAMIS KOMUT: Whitelist'te yok."}

        # Calistir
        proc = await asyncio.create_subprocess_shell(
            command,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()

        return {
            "success": proc.returncode == 0,
            "output": stdout.decode()[-5000],  # Max 5000 karakter
            "error": stderr.decode()[-2000] if proc.returncode != 0 else None
        }
```

---

## 6. Kaynak Izleme (Resource Monitor)

```python
class ResourceMonitor:
    async def get_current(self) -> dict:
        import psutil
        return {
            "cpu_usage_percent": psutil.cpu_percent(interval=1),
            "memory_total_gb": round(psutil.virtual_memory().total / (1024**3), 1),
            "memory_usage_percent": psutil.virtual_memory().percent,
            "disk_free_gb": round(psutil.disk_usage('/').free / (1024**3), 1),
            "disk_usage_percent": psutil.disk_usage('/').percent,
            "load_average": os.getloadavg(),  # 1min, 5min, 15min
        }

    async def check_alerts(self) -> list:
        resources = await self.get_current()
        alerts = []
        if resources["disk_usage_percent"] > 85:
            alerts.append(f"Disk kullanimi yuksek: %{resources['disk_usage_percent']}")
        if resources["memory_usage_percent"] > 90:
            alerts.append(f"RAM kullanimi yuksek: %{resources['memory_usage_percent']}")
        return alerts
```

---

## 7. Kurulum

### 7.1 macOS Kurulum (install_mac.sh)

```bash
#!/bin/bash
set -e

echo "RafRaf Agent - macOS Kurulumu"

# Python 3.11+ kontrolu
python3 --version || { echo "Python 3.11+ gerekli"; exit 1; }

# Virtual environment
python3 -m venv ~/.rafraf-agent/venv
source ~/.rafraf-agent/venv/bin/activate

# Bagimliliklar
pip install -r requirements.txt

# Playwright (sadece Chromium)
playwright install chromium

# Maestro (eger yoksa)
if ! command -v maestro &> /dev/null; then
    curl -Ls "https://get.maestro.mobile.dev" | bash
fi

# Docker kontrolu
docker --version || echo "UYARI: Docker Desktop kurulu degil"

# Konfigürasyon dosyalari
mkdir -p ~/.rafraf-agent/config
cp config/agent.yaml.example ~/.rafraf-agent/config/agent.yaml
echo "ONEMLI: ~/.rafraf-agent/config/agent.yaml dosyasini duzenleyin"

# LaunchAgent (otomatik baslatma)
cp launchd/com.rafraf.agent.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.rafraf.agent.plist

echo "Kurulum tamamlandi. Agent otomatik baslatildi."
```

### 7.2 Ubuntu Kurulum (install_ubuntu.sh)

```bash
#!/bin/bash
set -e

echo "RafRaf Agent - Ubuntu Kurulumu"

# Python 3.11+
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3-pip

# Virtual environment
python3.11 -m venv /opt/rafraf-agent/venv
source /opt/rafraf-agent/venv/bin/activate

# Bagimliliklar
pip install -r requirements.txt

# Playwright (sadece Chromium, headless)
playwright install chromium
playwright install-deps chromium

# Docker kontrolu
docker --version || { echo "Docker kurulumu gerekli"; exit 1; }

# Konfigürasyon
mkdir -p /opt/rafraf-agent/config
cp config/agent.yaml.example /opt/rafraf-agent/config/agent.yaml
echo "ONEMLI: /opt/rafraf-agent/config/agent.yaml dosyasini duzenleyin"

# Systemd service
sudo cp systemd/rafraf-agent.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable rafraf-agent
sudo systemctl start rafraf-agent

echo "Kurulum tamamlandi. Agent systemd servisi olarak baslatildi."
```

### 7.3 macOS LaunchAgent

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "...">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.rafraf.agent</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/atakan/.rafraf-agent/venv/bin/python</string>
        <string>-m</string>
        <string>agent.main</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/atakan/projects/rafraf-agent</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/rafraf-agent.stdout.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/rafraf-agent.stderr.log</string>
</dict>
</plist>
```

### 7.4 Ubuntu Systemd Service

```ini
[Unit]
Description=RafRaf Host Agent
After=network.target docker.service
Wants=docker.service

[Service]
Type=simple
User=atakan
WorkingDirectory=/opt/rafraf-agent
ExecStart=/opt/rafraf-agent/venv/bin/python -m agent.main
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

# Guvenlik
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/tmp/rafraf /home/atakan/projects

[Install]
WantedBy=multi-user.target
```

---

## 8. Mac Uyku / Kapali Durumu

Mac'ler her zaman acik olmayabilir. Bu durum icin stratejiler:

### 8.1 Uyku Modundan Cikis

- **caffeinate komutu:** Agent calismaya basladiginda `caffeinate -i` ile uyku engellenir (sadece aktif komut varken)
- **Power Nap:** macOS ayarlarindan Power Nap aktif ise, uyku modunda bile network erisimi olur
- **Wake-on-LAN:** Ayni agtaki baska bir cihazdan Mac uyandirilabilir

### 8.2 Offline Durumunda

```
Backend: macbook-pro'dan 3 heartbeat gelmiyor
    │
    ▼
Backend: macbook-pro'yu "offline" isaretle
    │
    ▼
AI bir tool calistirmak istiyor (macbook-pro'da)
    │
    ├── fallback_host var mi? → Evet → fallback host'a gonder
    │
    └── fallback_host yok → Kullaniciya bildir:
        "MacBook Pro suanda cevimdisi. Lutfen Mac'i acin
         veya baska bir host'ta calistirayim mi?"
```

### 8.3 Otomatik Baslatma

- **macOS:** LaunchAgent ile login'de otomatik baslar
- **Ubuntu:** Systemd ile boot'ta otomatik baslar
- Agent basladiginda otomatik olarak backend'e baglanir ve register olur

---

## 9. Guvenlik

### 9.1 Agent Authentication

- Her agent benzersiz bir API key ile auth olur
- API key agent.yaml'da saklanir (dosya izinleri: 600)
- Backend tarafinda API key hash'i host_agents tablosunda tutulur
- Key rotation: 90 gunde bir

### 9.2 Komut Guvenliği

- Tum komutlar whitelist/blacklist kontrolunden gecer (Shell Runner bakinca)
- Agent sadece backend'ten gelen komutlari calistirir (dis erisim yok)
- Onay gerektiren komutlar agent tarafindan tespit edilir ve backend'e bildirilir
- Max concurrent command limiti: 3 (DoS koruması)

### 9.3 Network Guvenliği

- Tum iletisim TLS 1.3 uzerinden (WSS)
- Agent sadece outbound baglanti yapar (inbound port acmak gerekmez)
- Backend URL ve API key disinda hassas bilgi agent'ta tutulmaz

---

## 10. Bagimliliklar (requirements.txt)

```
# Core
websockets>=12.0
asyncio

# Docker
docker>=7.0

# Playwright
playwright>=1.42

# AWS
boto3>=1.34

# Monitoring
psutil>=5.9

# Konfigürasyon
pyyaml>=6.0
pydantic>=2.0

# Logging
structlog>=24.0
```

### 10.1 Ek Bagimliliklar (Host Bazli)

**macOS (Maestro):**
```
# Maestro CLI ayri kurulur (npm/homebrew degil, kendi installer)
# Xcode: App Store'dan kurulu olmali
# iOS Simulator: Xcode ile birlikte gelir
```

**Ubuntu:**
```
# Playwright system deps
# apt: libnss3, libnspr4, libatk1.0-0, libatk-bridge2.0-0, libcups2, libdrm2, libxkbcommon0, libxcomposite1, libxdamage1, libxrandr2, libgbm1, libpango-1.0-0, libcairo2, libasound2
```

---

## 11. Test

### 11.1 Unit Tests

- Connection manager: baglanti, reconnect, heartbeat
- Command handler: routing, timeout, hata yonetimi
- Security: whitelist/blacklist dogrulama
- Resource monitor: metrik toplama

### 11.2 Integration Tests

- Agent ↔ Backend WebSocket iletisimi
- Docker komut calistirma ve sonuc dondurme
- Playwright screenshot alma ve S3 upload
- Maestro flow calistirma (mocking ile)

### 11.3 End-to-End Test

- iOS app'ten komut gonder → Backend → Agent → Tool calistir → Sonuc geri gelsin
- Tum zincirin calistigini dogrula

---

*Bu dokuman RafRaf serisinin 8/8 numarali ve son dokumanidir.*
*Onceki: 07_Security_Permissions_Cost_Analysis.md*
