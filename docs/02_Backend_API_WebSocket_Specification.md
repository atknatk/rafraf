# RafRaf — Backend API & WebSocket Specification

**Document 2/8** | Version 1.1 | March 2026

---

## 1. Genel Bakis

Backend, tum sistemin kalbidir. FastAPI uzerinde WebSocket sunucusu olarak calisir, Claude API ile iletisim kurar, tool'lari yonetir ve iOS app ile gercek zamanli veri alisverisi saglar.

### 1.1 Teknoloji Secimi

| Bileşen | Teknoloji | Versiyon |
|---------|-----------|----------|
| Framework | FastAPI | 0.100+ |
| WebSocket | FastAPI WebSocket (Starlette) | Built-in |
| ASGI Server | Uvicorn | Latest |
| Task Queue | asyncio (built-in) | Python 3.12 |
| Cache | Redis (aioredis) | 7 |
| Database | PostgreSQL 16 + pgvector | 16 |
| ORM | SQLAlchemy 2.0+ async (asyncpg) | 2.0+ |
| Validation | Pydantic v2 | 2.0+ |
| Python | Python | 3.12 |

### 1.2 Neden FastAPI?

- Async native: `async def` tum endpoint ve servisler, asyncpg (DB), aioredis (cache) — WebSocket ve Claude API cagrilari non-blocking
- Python ekosistemi: Claude Agent SDK, mem0, Docker SDK, Playwright hepsi Python
- Type-safe: Pydantic v2 modelleri ile veri validasyonu (domain/entity modellerde `frozen=True`)
- Auto-docs: Swagger/OpenAPI otomatik dokumantasyon
- Performans: Starlette tabanli, Node.js ile karsilastirilabilir hiz

---

## 2. Proje Yapisi (Dizin Agaci)

```
apps/backend/
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI app, startup/shutdown
│   ├── config.py                  # Ortam degiskenleri, yapilandirma
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes/                # WebSocket, health, webhooks endpoints
│   │       ├── __init__.py
│   │       ├── websocket.py       # WebSocket endpoint ve handler
│   │       ├── health.py          # Health check endpoint
│   │       └── webhooks.py        # GitHub webhook receiver
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   └── security.py            # JWT, auth (token olusturma/dogrulama, rate limiting)
│   │
│   ├── services/                  # Business logic
│   │   ├── __init__.py
│   │   ├── stt_service.py         # Deepgram STT entegrasyonu
│   │   ├── tts_service.py         # OpenAI TTS entegrasyonu
│   │   ├── notification.py        # Push notification servisi (APNs)
│   │   └── cost_tracker.py        # API maliyet takibi
│   │
│   ├── repositories/              # DB access (SQLAlchemy async)
│   │   ├── __init__.py
│   │   ├── project_repo.py
│   │   ├── session_repo.py
│   │   └── audit_repo.py
│   │
│   ├── schemas/                   # Pydantic v2 request/response models
│   │   ├── __init__.py
│   │   ├── messages.py            # WebSocket mesaj modelleri (Pydantic v2)
│   │   ├── projects.py            # Proje request/response modelleri
│   │   ├── tools.py               # Tool input/output modelleri
│   │   └── audit.py               # Audit log modelleri
│   │
│   ├── models/                    # SQLAlchemy DB models
│   │   ├── __init__.py
│   │   ├── project.py
│   │   ├── session.py
│   │   ├── message.py
│   │   ├── host_agent.py
│   │   └── audit.py
│   │
│   ├── orchestrator/              # Claude Agent SDK integration
│   │   ├── __init__.py
│   │   ├── agent.py               # Claude Agent SDK entegrasyonu
│   │   ├── tool_registry.py       # Tool tanimlari ve dispatch
│   │   └── approval.py            # Onay sistemi yonetimi
│   │
│   ├── tools/                     # Claude tools (github, s3, memory, cost)
│   │   ├── __init__.py
│   │   ├── docker_tool.py         # Docker SDK islemleri
│   │   ├── github_tool.py         # GitHub API islemleri
│   │   ├── playwright_tool.py     # Playwright web test
│   │   ├── maestro_tool.py        # Maestro mobil test
│   │   ├── shell_tool.py          # Shell komut calistirma
│   │   └── s3_tool.py             # AWS S3 dosya islemleri
│   │
│   ├── memory/                    # mem0 integration
│   │   ├── __init__.py
│   │   ├── mem0_client.py         # mem0 SDK entegrasyonu
│   │   ├── project_memory.py      # Proje bazli hafiza yonetimi
│   │   └── conversation.py        # Conversation history yonetimi
│   │
│   └── db/
│       ├── __init__.py
│       ├── database.py            # Async DB baglantisi (asyncpg)
│       └── migrations/            # Alembic migration dosyalari
│
├── tests/
│   ├── __init__.py
│   ├── test_websocket.py
│   ├── test_orchestrator.py
│   ├── test_tools.py
│   └── test_memory.py
│
├── pyproject.toml
├── .env.example
└── README.md
```

> **Not:** Docker ve K8s konfigurasyonlari `infra/` dizininde yer alir (bkz. repo root yapisi).

---

## 3. WebSocket Protokolu

### 3.1 Baglanti Kurulumu

```
WSS://api.rafraf.example.com/ws?token={JWT_TOKEN}
```

**Baglanti Akisi:**
1. iOS app JWT token ile WebSocket baglantisi acar
2. Server token'i dogrular (JWT verify)
3. Baglanti basarili ise `connection_ack` mesaji gonderir
4. Heartbeat baslar (30 saniyede bir ping/pong)
5. Baglanti koparsa iOS app otomatik reconnect yapar (exponential backoff)

### 3.2 Mesaj Formati

Tum mesajlar JSON formatindadir.

**Base Message Schema:**

```json
{
  "id": "msg_uuid_v4",
  "type": "text | voice | screenshot | question | status | action_result | error | progress | approval_response",
  "content": "...",
  "metadata": {
    "timestamp": "2026-03-01T10:30:00Z",
    "session_id": "session_uuid",
    "project_id": "project-x",
    "message_id": "msg_uuid",
    "direction": "client_to_server | server_to_client"
  },
  "attachments": [
    {
      "type": "image | file | audio",
      "url": "s3://bucket/path",
      "mime_type": "image/png",
      "size_bytes": 102400
    }
  ]
}
```

### 3.3 Client → Server Mesaj Tipleri

**text — Metin mesaji:**
```json
{
  "id": "msg_001",
  "type": "text",
  "content": "Proje X'in durumunu kontrol et",
  "metadata": { "timestamp": "...", "session_id": "...", "direction": "client_to_server" }
}
```

**voice — Ses mesaji:**
```json
{
  "id": "msg_002",
  "type": "voice",
  "content": "Proje X'i Docker'da calistir",
  "metadata": {
    "timestamp": "...",
    "session_id": "...",
    "direction": "client_to_server",
    "original_audio_url": "s3://bucket/audio/msg_002.webm",
    "stt_provider": "deepgram",
    "stt_confidence": 0.95,
    "language": "tr"
  }
}
```

**approval_response — Onay cevabi:**
```json
{
  "id": "msg_003",
  "type": "approval_response",
  "content": {
    "approval_id": "approval_001",
    "decision": "approved",
    "note": "Deploy et"
  },
  "metadata": { "timestamp": "...", "session_id": "...", "direction": "client_to_server" }
}
```

**file_upload — Dosya gonderme:**
```json
{
  "id": "msg_004",
  "type": "file_upload",
  "content": {
    "filename": "mockup.png",
    "s3_url": "s3://bucket/uploads/mockup.png",
    "mime_type": "image/png",
    "size_bytes": 204800
  },
  "metadata": { "timestamp": "...", "session_id": "...", "direction": "client_to_server" }
}
```

### 3.4 Server → Client Mesaj Tipleri

**text — AI metin cevabi:**
```json
{
  "id": "msg_101",
  "type": "text",
  "content": "Proje X'in durumu: 3/5 task tamamlandi. Docker servisleri calisiyor. Son commit 2 saat once.",
  "metadata": {
    "timestamp": "...",
    "session_id": "...",
    "direction": "server_to_client",
    "model_used": "claude-sonnet-4-5",
    "tokens_used": { "input": 1500, "output": 200 }
  }
}
```

**voice — AI sesli cevap:**
```json
{
  "id": "msg_102",
  "type": "voice",
  "content": "Proje X basariyla Docker'da calistirildi.",
  "metadata": {
    "timestamp": "...",
    "session_id": "...",
    "direction": "server_to_client",
    "audio_url": "s3://bucket/audio/response_102.mp3",
    "tts_provider": "openai",
    "duration_seconds": 3.5
  }
}
```

**screenshot — Ekran goruntusu:**
```json
{
  "id": "msg_103",
  "type": "screenshot",
  "content": {
    "description": "Proje X ana sayfasi - login ekrani",
    "source": "playwright",
    "url": "http://localhost:3000",
    "viewport": { "width": 1920, "height": 1080 }
  },
  "attachments": [
    {
      "type": "image",
      "url": "s3://bucket/screenshots/proj-x-login-20260301.png",
      "mime_type": "image/png",
      "size_bytes": 153600
    }
  ]
}
```

**question — Interaktif soru:**
```json
{
  "id": "msg_104",
  "type": "question",
  "content": {
    "approval_id": "approval_001",
    "question": "Proje X'i production ortamina deploy etmek istiyor musunuz?",
    "context": "Son testler basarili. 3 yeni feature ve 2 bug fix mevcut.",
    "options": [
      { "id": "approve", "label": "Onayla", "style": "primary" },
      { "id": "reject", "label": "Reddet", "style": "danger" },
      { "id": "detail", "label": "Detaylari Goster", "style": "secondary" }
    ],
    "timeout_seconds": 300,
    "category": "deploy"
  }
}
```

**status — Proje durum karti:**
```json
{
  "id": "msg_105",
  "type": "status",
  "content": {
    "project_id": "project-x",
    "project_name": "Project X",
    "overall_status": "healthy",
    "details": {
      "issues": { "open": 5, "in_progress": 2, "done": 12 },
      "docker": { "status": "running", "containers": 3, "healthy": 3 },
      "last_deploy": "2026-02-28T14:30:00Z",
      "test_status": { "passed": 45, "failed": 2, "skipped": 1 },
      "last_commit": { "message": "fix: login redirect bug", "author": "ai-agent", "time": "2026-03-01T08:15:00Z" }
    }
  }
}
```

**progress — Ilerleme bildirimi:**
```json
{
  "id": "msg_106",
  "type": "progress",
  "content": {
    "task": "Docker build baslatiliyor...",
    "step": 2,
    "total_steps": 5,
    "percentage": 40,
    "details": "Layer 3/7 indiriliyor"
  }
}
```

**action_result — Komut sonucu:**
```json
{
  "id": "msg_107",
  "type": "action_result",
  "content": {
    "tool": "docker",
    "action": "compose_up",
    "success": true,
    "output": "3 container basariyla baslatildi",
    "duration_seconds": 12.5,
    "details": {
      "containers": [
        { "name": "web", "status": "running", "port": 3000 },
        { "name": "api", "status": "running", "port": 8080 },
        { "name": "db", "status": "running", "port": 5432 }
      ]
    }
  }
}
```

**error — Hata mesaji:**
```json
{
  "id": "msg_108",
  "type": "error",
  "content": {
    "error_code": "DOCKER_BUILD_FAILED",
    "message": "Docker build islemi basarisiz oldu",
    "details": "Step 5/8: npm install failed - ENOMEM",
    "suggestion": "Container memory limiti arttirilabilir veya node_modules cache kullanilabilir",
    "recoverable": true
  }
}
```

---

## 4. Host Agent WebSocket Protokolu (YENI)

iOS app ile backend arasindaki iletisime ek olarak, host agent'lar da backend'e WebSocket ile baglanir. Ayri bir endpoint ve mesaj protokolu kullanir.

### 4.1 Agent Baglanti Endpoint'i

```
WSS://api.rafraf.example.com/ws/agent?api_key={AGENT_API_KEY}&host_id={HOST_ID}
```

### 4.2 Agent Registration (Baglanti Kurulumu)

Agent ilk baglandiginda kendini tanitir:

```json
{
  "type": "agent_register",
  "host_id": "macbook-pro",
  "content": {
    "hostname": "Atakan-MacBook-Pro",
    "os": "macOS",
    "os_version": "15.3",
    "arch": "arm64",
    "capabilities": ["docker", "playwright", "maestro_ios", "shell", "xcode"],
    "projects": ["project-x", "project-z"],
    "resources": {
      "cpu_cores": 10,
      "memory_gb": 32,
      "disk_free_gb": 120
    },
    "agent_version": "1.0.0"
  }
}
```

Backend cevabi:

```json
{
  "type": "agent_registered",
  "content": {
    "status": "ok",
    "heartbeat_interval_seconds": 30,
    "assigned_projects": ["project-x", "project-z"]
  }
}
```

### 4.3 Agent Heartbeat

Her 30 saniyede agent durumunu bildirir:

```json
{
  "type": "agent_heartbeat",
  "host_id": "macbook-pro",
  "content": {
    "status": "online",
    "uptime_seconds": 3600,
    "active_tasks": 0,
    "resources": {
      "cpu_usage_percent": 23,
      "memory_usage_percent": 45,
      "disk_free_gb": 118
    },
    "docker_running_containers": 3
  }
}
```

### 4.4 Backend → Agent: Komut Gonderme

```json
{
  "type": "agent_command",
  "command_id": "cmd_uuid",
  "host_id": "macbook-pro",
  "content": {
    "tool": "docker_manager",
    "action": "compose_up",
    "project_slug": "project-x",
    "params": {
      "detached": true
    },
    "timeout_seconds": 60
  }
}
```

### 4.5 Agent → Backend: Komut Sonucu

```json
{
  "type": "agent_command_result",
  "command_id": "cmd_uuid",
  "host_id": "macbook-pro",
  "content": {
    "success": true,
    "output": "3 container basariyla baslatildi",
    "duration_ms": 12500,
    "attachments": [
      {
        "type": "screenshot",
        "s3_url": "s3://bucket/screenshots/project-x/homepage.png"
      }
    ]
  }
}
```

### 4.6 Agent → Backend: Komut Ilerleme (Uzun Islemler)

```json
{
  "type": "agent_command_progress",
  "command_id": "cmd_uuid",
  "host_id": "macbook-pro",
  "content": {
    "step": "Docker build: Layer 5/8",
    "percentage": 62
  }
}
```

### 4.7 Host Durumu Degisikligi

Agent kapanirken veya hata durumunda:

```json
{
  "type": "agent_status_change",
  "host_id": "macbook-pro",
  "content": {
    "status": "shutting_down",
    "reason": "User initiated shutdown",
    "active_tasks_cancelled": 0
  }
}
```

Backend, 3 ardisik heartbeat kacirilirsa host'u "offline" olarak isaretler ve kullaniciya bildirir.

---

## 5. REST API Endpoints

WebSocket disinda bazi islemler icin REST endpoint'ler de bulunur.

### 5.1 Health & Status

```
GET  /health                    → Sistem saglilk durumu
GET  /health/detailed           → Tum servislerin detayli durumu
```

### 5.2 Authentication

```
POST /auth/token                → JWT token olustur (API key ile)
POST /auth/refresh              → Token yenile
POST /auth/revoke               → Token iptal et
```

### 5.3 Projects

```
GET  /api/projects              → Tum projelerin listesi
GET  /api/projects/{id}         → Tek proje detayi
PUT  /api/projects/{id}         → Proje bilgilerini guncelle
GET  /api/projects/{id}/status  → Proje canli durumu
```

### 5.4 Files (S3 Proxy)

```
POST /api/files/upload-url      → S3 pre-signed upload URL al
POST /api/files/download-url    → S3 pre-signed download URL al
GET  /api/files/list            → Paylasilan dosyalari listele
```

### 5.5 Webhooks (GitHub)

```
POST /webhooks/github           → GitHub event receiver
```

### 5.6 Host Agents (REST)

```
GET  /api/agents                → Bagli tum host agent'larin listesi ve durumu
GET  /api/agents/{host_id}      → Tek agent detayi (kaynak kullanimi, projeler)
POST /api/agents/{host_id}/wake → Wake-on-LAN veya bildirim gonder (opsiyonel)
```

### 5.7 Admin

```
GET  /admin/costs               → API maliyet raporu
GET  /admin/audit               → Audit log
GET  /admin/sessions            → Aktif session'lar
GET  /admin/hosts               → Host saglik dashboard
```

---

## 6. Veritabani Semasi

### 6.1 PostgreSQL Tablolari

**host_agents — Host agent tanimlari:**
```sql
CREATE TABLE host_agents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    host_id VARCHAR(50) UNIQUE NOT NULL,       -- "macbook-pro", "ubuntu-dev"
    hostname VARCHAR(100) NOT NULL,
    os VARCHAR(20) NOT NULL,                    -- "macos", "ubuntu"
    os_version VARCHAR(20),
    arch VARCHAR(20),                           -- "arm64", "x86_64"
    capabilities JSONB NOT NULL,                -- ["docker", "playwright", "maestro_ios"]
    api_key_hash VARCHAR(255) NOT NULL,
    status VARCHAR(20) DEFAULT 'offline',       -- online | offline | shutting_down
    last_heartbeat_at TIMESTAMP,
    last_resources JSONB,                       -- CPU, RAM, disk kullanimi
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

**projects — Proje tanimlari:**
```sql
CREATE TABLE projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL,
    slug VARCHAR(50) UNIQUE NOT NULL,
    github_repo VARCHAR(255) NOT NULL,
    tech_stack JSONB NOT NULL,         -- ["nodejs", "nextjs", "postgresql"]
    primary_host_id VARCHAR(50) REFERENCES host_agents(host_id),
    fallback_host_id VARCHAR(50) REFERENCES host_agents(host_id),
    project_path VARCHAR(255),          -- Host uzerindeki proje dizini
    docker_compose_path VARCHAR(255),
    playwright_config JSONB,
    maestro_config JSONB,
    environment VARCHAR(20) DEFAULT 'development',
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

**sessions — Konusma oturumlari:**
```sql
CREATE TABLE sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(50) NOT NULL,
    started_at TIMESTAMP DEFAULT NOW(),
    ended_at TIMESTAMP,
    message_count INTEGER DEFAULT 0,
    total_tokens_used JSONB DEFAULT '{"input": 0, "output": 0}',
    total_cost_usd DECIMAL(10, 4) DEFAULT 0
);
```

**messages — Mesaj gecmisi:**
```sql
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES sessions(id),
    type VARCHAR(30) NOT NULL,
    direction VARCHAR(20) NOT NULL,     -- client_to_server | server_to_client
    content JSONB NOT NULL,
    metadata JSONB,
    model_used VARCHAR(50),
    tokens_input INTEGER,
    tokens_output INTEGER,
    cost_usd DECIMAL(10, 6),
    created_at TIMESTAMP DEFAULT NOW()
);
```

**audit_log — Islem gecmisi:**
```sql
CREATE TABLE audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES sessions(id),
    tool_name VARCHAR(50) NOT NULL,
    action VARCHAR(100) NOT NULL,
    project_id UUID REFERENCES projects(id),
    input_params JSONB,
    output_result JSONB,
    success BOOLEAN NOT NULL,
    error_message TEXT,
    duration_ms INTEGER,
    approval_required BOOLEAN DEFAULT FALSE,
    approved_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);
```

**cost_tracking — Maliyet takibi:**
```sql
CREATE TABLE cost_tracking (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    date DATE NOT NULL,
    service VARCHAR(50) NOT NULL,        -- claude_api, deepgram, openai_tts, s3
    model VARCHAR(50),                    -- claude-sonnet-4-5, claude-haiku-4-5
    tokens_input BIGINT DEFAULT 0,
    tokens_output BIGINT DEFAULT 0,
    api_calls INTEGER DEFAULT 0,
    cost_usd DECIMAL(10, 4) NOT NULL,
    UNIQUE(date, service, model)
);
```

**approval_requests — Onay talepleri:**
```sql
CREATE TABLE approval_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES sessions(id),
    project_id UUID REFERENCES projects(id),
    tool_name VARCHAR(50) NOT NULL,
    action VARCHAR(100) NOT NULL,
    description TEXT NOT NULL,
    params JSONB,
    status VARCHAR(20) DEFAULT 'pending',   -- pending | approved | rejected | expired
    timeout_at TIMESTAMP,
    responded_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);
```

---

## 7. Konfigürasyon

### 7.1 Ortam Degiskenleri (.env)

```env
# App
APP_ENV=production
APP_HOST=0.0.0.0
APP_PORT=8000
APP_DEBUG=false
APP_SECRET_KEY=your-secret-key-here

# Claude API
CLAUDE_API_KEY=sk-ant-...
CLAUDE_DEFAULT_MODEL=claude-sonnet-4-5-20250929
CLAUDE_FALLBACK_MODEL=claude-haiku-4-5-20251001

# Deepgram
DEEPGRAM_API_KEY=...

# OpenAI TTS
OPENAI_API_KEY=sk-...

# Database
DATABASE_URL=postgresql+asyncpg://user:pass@postgres:5432/rafraf

# Redis
REDIS_URL=redis://redis:6379/0

# AWS
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=eu-west-1
S3_BUCKET=rafraf-files

# GitHub
GITHUB_TOKEN=ghp_...
GITHUB_WEBHOOK_SECRET=webhook-secret

# mem0
MEM0_API_URL=http://mem0-server:8080

# Rate Limiting
RATE_LIMIT_MESSAGES_PER_MINUTE=30
RATE_LIMIT_TOOLS_PER_MINUTE=20

# Cost Alerts
COST_ALERT_DAILY_USD=10
COST_ALERT_MONTHLY_USD=200

# Approval Timeout
APPROVAL_TIMEOUT_SECONDS=300
```

### 7.2 Proje Konfigurasyonu (projects.yaml)

```yaml
projects:
  - slug: project-x
    name: "Project X"
    github_repo: "username/project-x"
    tech_stack: ["nextjs", "nodejs", "postgresql"]
    environment: production
    docker:
      compose_file: "docker-compose.yml"
      health_check_url: "http://localhost:3000/health"
    playwright:
      base_url: "http://localhost:3000"
      test_dir: "tests/e2e"
    maestro:
      ios_app_id: "com.company.projectx"
      android_app_id: "com.company.projectx"

  - slug: project-y
    name: "Project Y"
    github_repo: "username/project-y"
    tech_stack: ["python", "fastapi", "mongodb"]
    environment: development
    docker:
      compose_file: "docker-compose.dev.yml"
      health_check_url: "http://localhost:8080/health"
    playwright:
      base_url: "http://localhost:8080"
```

---

## 8. Error Handling Stratejisi

### 8.1 Hata Kategorileri

| Kategori | Ornek | Aksiyon |
|----------|-------|---------|
| Recoverable | Docker timeout, API rate limit | Otomatik retry (max 3) |
| Non-recoverable | Invalid config, auth failure | Kullaniciya hata bildir |
| Approval-needed | Deploy hatasi, veri kaybi riski | Kullaniciya sor |
| System-critical | DB baglanti kaybi, OOM | Alert gonder, graceful shutdown |

### 8.2 Retry Politikasi

- **Docker islemleri:** 3 retry, 5 saniye aralikla
- **API cagrilari (Claude, Deepgram vb.):** 3 retry, exponential backoff (1s, 2s, 4s)
- **GitHub API:** Rate limit'e takillirsa bekle (X-RateLimit-Reset header)
- **Playwright:** 2 retry, her retry'da page refresh

### 8.3 Graceful Degradation

- Claude API erisilemazse: Kullaniciya bildir, kuyruga al
- Deepgram erisilemazse: Sadece metin modu (ses devredisi)
- mem0 erisilemazse: Hafizasiz mod (sadece mevcut konusma)
- S3 erisilemazse: Screenshot'lar base64 olarak WebSocket'ten gonderilir
- Host Agent offline ise: Fallback host'a yonlendir, o da yoksa kullaniciya bildir
- Tum Host Agent'lar offline ise: Sadece cloud tool'lar (GitHub, S3) calisir

---

## 9. Performans Gereksinimleri

| Metrik | Hedef |
|--------|-------|
| WebSocket mesaj latency | < 100ms (server tarafli) |
| Claude API response (Sonnet) | < 5 saniye (tipik) |
| Claude API response (Haiku) | < 2 saniye (tipik) |
| Playwright screenshot | < 3 saniye |
| Docker compose up | < 30 saniye |
| STT processing | < 1 saniye (Deepgram streaming) |
| TTS generation | < 2 saniye |
| Concurrent WebSocket connections | 5+ (tek kullanici, birden fazla cihaz) |

---

*Bu dokuman RafRaf serisinin 2/8 numarali dokumanidir.*
*Onceki: 01_System_Architecture_Overview.md*
*Sonraki: 03_AI_Agent_Tool_Layer_Specification.md*
