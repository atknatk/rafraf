# Feature: Docker Runner (compose up/down/logs/health)

**Issue**: #14
**Faz**: F2
**Katmanlar**: agent
**Pipeline**: full
**Tarih**: 2026-03-02

## Ozet

Docker Compose islemlerini calistiran runner. Host Agent uzerinde konteyner baslatma (compose up), durdurma (compose down/restart), log okuma (streaming tail) ve saglik kontrolu (health check) islemlerini gerceklestirir. Backend'ten gelen komutlari Docker SDK for Python ve Compose v2 CLI uzerinden calistirir. Sadece izin verilen compose dosyalari ile calisabilir (guvenlik).

## Degisecek Dosyalar

### Agent (`apps/agent/`)
| Dosya | Islem | Aciklama |
|-------|-------|----------|
| `agent/runners/__init__.py` | MODIFY | BaseRunner ABC + runner registry |
| `agent/runners/base.py` | CREATE | BaseRunner abstract sinifi |
| `agent/runners/docker_runner.py` | CREATE | Docker Compose runner implementasyonu |
| `agent/core/config.py` | MODIFY | Docker-specific config alanlari (allowed compose files, resource limits) |
| `agent/core/protocol.py` | MODIFY | Docker command/result mesaj modelleri |

## API Endpoints

Bu feature yalnizca agent katmanini etkiler. Yeni REST veya WebSocket endpoint'i eklenmez. Docker komutlari mevcut `agent_command` / `agent_command_result` WS mesaj akisi uzerinden tasinir.

### WebSocket Messages (mevcut akis uzerinden)

Backend'ten agent'a gelen `agent_command` mesaji icerisindeki tool/action parametreleri:

| Tool | Action | Params | Aciklama |
|------|--------|--------|----------|
| `docker` | `compose_up` | `project_slug`, `services?`, `detach?` | Compose up -d |
| `docker` | `compose_down` | `project_slug`, `remove_volumes?` | Compose down |
| `docker` | `compose_restart` | `project_slug`, `services?` | Compose restart |
| `docker` | `compose_logs` | `project_slug`, `service?`, `tail?`, `since?` | Log okuma |
| `docker` | `health_check` | `project_slug` | Container saglik kontrolu |
| `docker` | `container_status` | `project_slug` | Container durumlarini raporla |

## Data Model

### Pydantic Models

```python
class DockerCommandParams(BaseModel):
    """Docker komutu parametreleri."""
    model_config = ConfigDict(frozen=True)

    project_slug: str
    action: str
    services: list[str] | None = None
    tail: int = 100
    since: str | None = None
    remove_volumes: bool = False
    detach: bool = True

class DockerCommandResult(BaseModel):
    """Docker komut sonucu."""
    model_config = ConfigDict(frozen=True)

    success: bool
    output: str
    error: str | None = None
    containers: list[ContainerInfo] | None = None
    execution_time_ms: int

class ContainerInfo(BaseModel):
    """Tek bir container'in durum bilgisi."""
    model_config = ConfigDict(frozen=True)

    name: str
    status: str  # running, exited, paused, restarting
    health: str | None = None  # healthy, unhealthy, starting, none
    image: str
    ports: list[str]
    created_at: str
    started_at: str | None = None

class ProjectConfig(BaseModel):
    """Proje compose konfigurasyonu."""
    model_config = ConfigDict(frozen=True)

    slug: str
    path: str
    docker_compose: str = "docker-compose.yml"
```

## Business Rules

1. Sadece `allowed_compose_files` listesindeki compose dosyalari calistirabilir
2. Proje slug'inin projects_config'de tanimli olmasi zorunlu
3. Compose dosyasinin belirtilen path'te fiziksel olarak bulunmasi zorunlu
4. `compose_up` varsayilan olarak detached modda calisir (`-d`)
5. `compose_logs` varsayilan olarak son 100 satiri dondurur
6. Tum komutlar icin timeout uygulanir (varsayilan: 120 saniye)
7. Resource limitleri: max CPU ve RAM siniri konfigurasyon uzerinden belirlenir
8. Her komut sonucunda `execution_time_ms` raporlanir
9. Container health check `docker inspect` uzerinden `Health.Status` alanini okur

## Test Requirements

### Agent
- [ ] Unit test: DockerRunner compose_up basari senaryosu
- [ ] Unit test: DockerRunner compose_down basari senaryosu
- [ ] Unit test: DockerRunner compose_restart basari senaryosu
- [ ] Unit test: DockerRunner compose_logs basari senaryosu
- [ ] Unit test: DockerRunner health_check basari senaryosu
- [ ] Unit test: DockerRunner container_status basari senaryosu
- [ ] Unit test: Gecersiz project_slug hata senaryosu
- [ ] Unit test: Izin verilmeyen compose dosyasi hata senaryosu
- [ ] Unit test: Compose dosyasi bulunamadi hata senaryosu
- [ ] Unit test: Timeout senaryosu
- [ ] Unit test: BaseRunner abstract metod zorunlulugu
- [ ] Integration test: Docker SDK ile container health check

## Acceptance Criteria

- [ ] docker compose up/down/restart komutlari calistirabilir
- [ ] Container health check yapilabilir
- [ ] Log streaming (tail) desteklenir
- [ ] Container status raporlamasi calisir
- [ ] Timeout handling (uzun suren islemler)
- [ ] Resource limitleri (CPU, RAM) konfigurasyon uzerinden belirlenir
- [ ] Sadece izin verilen compose dosyalari calistirilabilir
- [ ] Unit + integration testler yazildi
- [ ] Coverage >= 80%
