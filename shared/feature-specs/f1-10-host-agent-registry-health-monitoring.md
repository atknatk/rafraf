# Feature: Host Agent Registry + Health Monitoring

**Issue**: #10
**Faz**: F1
**Katmanlar**: backend
**Pipeline**: full
**Tarih**: 2026-03-02

## Ozet

Host Agent'larin backend'e WebSocket uzerinden kaydolmasi, durum takibi ve saglik kontrolu sistemi. Backend, bagli agent'larin listesini tutar, heartbeat ile saglik durumlarini izler ve agent yeteneklerini (docker, playwright, maestro, shell) kaydeder. Birden fazla agent destegi ile farkli makinelerdeki islem kapasitelerinin merkezi yonetimini saglar.

## Degisecek Dosyalar

### Backend (`apps/backend/`)
| Dosya | Islem | Aciklama |
|-------|-------|----------|
| `app/models/agent.py` | CREATE | HostAgent SQLAlchemy modeli |
| `app/schemas/agent.py` | CREATE | Agent Pydantic request/response semalari |
| `app/services/agent_registry_service.py` | CREATE | Agent kayit, durum takibi ve saglik kontrolu business logic |
| `app/api/routes/agent_ws.py` | CREATE | Agent WebSocket endpoint (kayit + heartbeat + komut) |
| `app/api/routes/agents.py` | CREATE | REST endpoint: agent listesi ve durum sorgulama |
| `app/main.py` | MODIFY | Yeni router'lari ekle, lifespan'a stale agent temizleme gorevi ekle |
| `app/core/config.py` | MODIFY | Agent-related configuration settings ekle |

## API Endpoints

### REST
| Method | Path | Request | Response | Aciklama |
|--------|------|---------|----------|----------|
| GET | `/api/v1/agents` | Query: `status` (optional) | `AgentListResponse` | Kayitli agent listesi ve durumlari |
| GET | `/api/v1/agents/{host_id}` | - | `AgentDetailResponse` | Tek agent detayi |

### WebSocket Messages (Agent -> Backend)
| Direction | Type | Payload | Aciklama |
|-----------|------|---------|----------|
| agent->server | `agent_register` | `AgentRegisterPayload` | Agent kayit ve yetenek bildirimi |
| agent->server | `agent_heartbeat` | `AgentHeartbeatPayload` | Periyodik saglik raporu (30sn) |
| server->agent | `agent_register_ack` | `AgentRegisterAckPayload` | Kayit onay mesaji |
| server->agent | `agent_command` | `AgentCommandPayload` | Backend'ten agent'a komut gonderme |
| agent->server | `agent_command_result` | `AgentCommandResultPayload` | Komut sonucu raporu |

## Data Model

### PostgreSQL
```sql
CREATE TABLE host_agents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    host_id VARCHAR(100) NOT NULL UNIQUE,
    status VARCHAR(20) NOT NULL DEFAULT 'offline',
    capabilities JSONB NOT NULL DEFAULT '[]',
    last_heartbeat_at TIMESTAMPTZ,
    registered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_host_agents_status ON host_agents(status);
CREATE INDEX idx_host_agents_host_id ON host_agents(host_id);
```

### Pydantic Models
```python
class AgentStatus(StrEnum):
    ONLINE = "online"
    OFFLINE = "offline"
    BUSY = "busy"

class AgentCapability(StrEnum):
    DOCKER = "docker"
    PLAYWRIGHT = "playwright"
    MAESTRO_IOS = "maestro_ios"
    MAESTRO_ANDROID = "maestro_android"
    SHELL = "shell"
    XCODE_BUILD = "xcode_build"
    ANDROID_BUILD = "android_build"
    GIT = "git"
    PYTHON = "python"
    NODEJS = "nodejs"

class AgentRegisterPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    host_id: str
    capabilities: list[AgentCapability]
    os_info: str
    version: str

class AgentHeartbeatPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    host_id: str
    status: AgentStatus
    uptime_seconds: int
    active_tasks: int
    resources: ResourceInfo

class ResourceInfo(BaseModel):
    model_config = ConfigDict(frozen=True)
    cpu_usage_percent: float
    memory_usage_percent: float
    disk_usage_percent: float
    disk_free_gb: float

class AgentRegisterAckPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    host_id: str
    registered: bool
    server_time: str
    heartbeat_interval: int

class AgentSummary(BaseModel):
    model_config = ConfigDict(frozen=True)
    host_id: str
    status: AgentStatus
    capabilities: list[AgentCapability]
    last_heartbeat_at: str | None
    os_info: str | None
    uptime_seconds: int | None
    active_tasks: int | None
    resources: ResourceInfo | None

class AgentListResponse(BaseModel):
    agents: list[AgentSummary]
    total: int
    online_count: int

class AgentDetailResponse(BaseModel):
    host_id: str
    status: AgentStatus
    capabilities: list[AgentCapability]
    last_heartbeat_at: str | None
    registered_at: str
    os_info: str | None
    metadata: dict[str, object]
    uptime_seconds: int | None
    active_tasks: int | None
    resources: ResourceInfo | None
```

## Business Rules

1. Agent `agent_register` mesaji gondererek kaydolur. Eger ayni `host_id` ile kayit varsa, guncellenir (upsert).
2. Heartbeat interval 30 saniyedir. 3 ardisik heartbeat gelmezse (90sn) agent `offline` olarak isaretlenir.
3. Agent durumu: `online` (heartbeat aliyor), `offline` (heartbeat yok), `busy` (aktif task calistiriyor).
4. Agent WebSocket'e `X-API-Key` header ile baglanir. API key `agent_api_key` config ile dogrulanir.
5. REST endpoint'ler JWT auth ile korunur (sadece yetkili kullanicilar agent durumlarini gorebilir).
6. Stale agent temizleme: Backend lifespan'da periyodik gorev ile 90 saniyeden fazla heartbeat almamis agent'lar `offline` yapilir.
7. Birden fazla agent destegi: Farkli `host_id`'ler ile birden fazla agent ayni anda bagli olabilir.

## Test Requirements

### Backend
- [ ] Unit test: AgentRegistryService - register, heartbeat update, stale agent detection
- [ ] Unit test: Agent schema validation (register payload, heartbeat payload)
- [ ] Integration test: Agent WebSocket endpoint - connect, register, heartbeat, disconnect
- [ ] Integration test: REST endpoint - GET /api/v1/agents, GET /api/v1/agents/{host_id}
- [ ] Unit test: Agent auth (API key validation)

## Acceptance Criteria

- [ ] Agent registration endpoint (WebSocket) calisiyor
- [ ] Agent health check (heartbeat) 30sn aralikla aliniyor
- [ ] Agent capability reporting (hangi runner'lar mevcut) kaydediliyor
- [ ] Agent disconnect/reconnect handling calisiyor
- [ ] Multi-agent support (birden fazla makine) destekleniyor
- [ ] Agent durumu REST endpoint ile sorgulanabiliyor (GET /api/v1/agents)
- [ ] Unit + integration testler yazildi
- [ ] Coverage >= 80%
