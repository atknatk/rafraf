# Feature: Agent Daemon Base (WSS, Heartbeat, Reconnect)

**Issue**: #13
**Faz**: F2
**Katmanlar**: agent
**Pipeline**: full
**Tarih**: 2026-03-02

## Ozet

Host Agent daemon temel yapisi. Backend'e WSS ile baglanir, heartbeat gonderir, kopmalarda otomatik yeniden baglanir. Bu feature, Host Agent'in backend ile iletisim kurmasini saglayan temel altyapiyi olusturur. Agent, asyncio tabanli bir Python daemon olarak calisir ve systemd/launchd ile yonetilir.

## Degisecek Dosyalar

### Agent (`apps/agent/`)
| Dosya | Islem | Aciklama |
|-------|-------|----------|
| `agent/core/config.py` | CREATE | Agent konfigurasyonu (Pydantic Settings) |
| `agent/core/connection.py` | CREATE | WSS baglanti yonetimi (connect, reconnect, heartbeat) |
| `agent/core/protocol.py` | CREATE | Mesaj protokolu (register, heartbeat, message parsing) |
| `agent/main.py` | MODIFY | Daemon entry point guncelleme |
| `agent/monitoring/metrics.py` | CREATE | Sistem metrik toplama (CPU, RAM, disk) |

## WebSocket Messages

Mevcut `shared/api-contracts/ws/agent-messages.json` kontratina uyumlu mesajlar:

| Direction | Type | Payload | Aciklama |
|-----------|------|---------|----------|
| agent->server | `agent_register` | `{host_id, capabilities, os_info, version}` | Agent kayit ve yetenek bildirimi |
| server->agent | `agent_register_ack` | `{host_id, registered, server_time, heartbeat_interval}` | Kayit onay mesaji |
| agent->server | `agent_heartbeat` | `{host_id, status, uptime_seconds, active_tasks, resources}` | Periyodik saglik raporu |

## Data Model

### Pydantic Models (Agent)

```python
from pydantic import BaseModel, ConfigDict
from pydantic_settings import BaseSettings


class AgentConfig(BaseSettings):
    """Agent konfigurasyonu - environment variables'dan okunur."""
    host_id: str
    api_key: str
    backend_ws_url: str
    heartbeat_interval: int = 30
    reconnect_initial_delay: float = 1.0
    reconnect_max_delay: float = 60.0


class ResourceMetrics(BaseModel):
    """Sistem kaynak metrikleri - frozen domain model."""
    model_config = ConfigDict(frozen=True)

    cpu_usage_percent: float
    memory_usage_percent: float
    disk_usage_percent: float
    disk_free_gb: float


class AgentCapabilities(BaseModel):
    """Agent yetenek bildirimi - frozen domain model."""
    model_config = ConfigDict(frozen=True)

    docker: bool = False
    playwright: bool = False
    maestro_ios: bool = False
    maestro_android: bool = False
    shell: bool = False
    xcode_build: bool = False
    android_build: bool = False
    git: bool = False
    python: bool = False
    nodejs: bool = False
```

## Business Rules

1. WSS baglanti basarisiz olursa exponential backoff ile yeniden baglanma denemesi yapilir (1s, 2s, 4s, 8s, ..., max 60s)
2. Heartbeat her 30 saniyede bir gonderilir (backend'ten gelen `heartbeat_interval` degerine gore ayarlanabilir)
3. Auth token (API key) `X-API-Key` header ile gonderilir
4. Baglanti kuruldugunda `agent_register` mesaji gonderilir
5. `agent_register_ack` mesaji alindiginda heartbeat dongusu baslatilir
6. Graceful shutdown: SIGTERM/SIGINT sinyallerinde baglanti temiz kapatilir
7. Capability reporting: Agent hangi runner'lara sahip oldugunu kayit sirasinda bildirir
8. Baglanti kopmasi tespit edildiginde reconnect_delay sifirlanir ve yeniden baglanma baslar

## Test Requirements

### Agent
- [ ] Unit test: AgentConfig pydantic settings dogrulama
- [ ] Unit test: ResourceMetrics model olusturma ve frozen dogrulama
- [ ] Unit test: Protocol mesaj serialization/deserialization
- [ ] Unit test: Exponential backoff hesaplama
- [ ] Unit test: Capability list olusturma
- [ ] Integration test: WSS baglanti kurma (mock server ile)
- [ ] Integration test: Heartbeat gonderme dongusu
- [ ] Integration test: Reconnect senaryosu
- [ ] Integration test: Graceful shutdown

## Acceptance Criteria

- [ ] WSS baglanti kurma (backend'e)
- [ ] Heartbeat gonderme (30sn aralik)
- [ ] Otomatik reconnect (exponential backoff: 1s, 2s, 4s, 8s, max 60s)
- [ ] Graceful shutdown (SIGTERM/SIGINT)
- [ ] Capability reporting (mevcut runner'lar)
- [ ] Auth token ile baglanti
- [ ] Daemon mode (systemd/launchd uyumlu)
- [ ] Unit + integration testler yazildi
- [ ] Coverage >= 80%
