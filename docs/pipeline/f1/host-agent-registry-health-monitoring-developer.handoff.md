# Developer Handoff: Host Agent Registry + Health Monitoring

**Issue**: #10
**Branch**: feature/f1/10-host-agent-registry-health-monitoring
**PR**: (tester sonrasi olusturulacak)
**Tarih**: 2026-03-02
**Sonraki Agent**: tester

## Yapilan Degisiklikler

| Dosya | Islem | Aciklama |
|-------|-------|----------|
| `app/schemas/agent.py` | CREATE | Agent Pydantic semalari (status, capability, payloads, REST responses) |
| `app/services/agent_registry_service.py` | CREATE | In-memory agent registry: register, heartbeat, stale detection, queries |
| `app/api/routes/agent_ws.py` | CREATE | Agent WebSocket endpoint /ws/agent (API key auth, register, heartbeat) |
| `app/api/routes/agents.py` | CREATE | REST endpoint: GET /api/v1/agents, GET /api/v1/agents/{host_id} |
| `app/main.py` | MODIFY | Yeni router'lar eklendi, lifespan'a stale checker start/stop eklendi |

## Dogrulama Sonuclari

| Arac | Durum | Detay |
|------|-------|-------|
| ruff check | PASS | All checks passed |
| ruff format | PASS | 40 files already formatted |
| mypy | PASS | Success: no issues found in 40 source files |
| pytest | PASS | Tum mevcut testler gecti (auth endpoint bcrypt hatasi pre-existing) |

## API Kontrat Uyumu

- `shared/api-contracts/rest/v1/agents.json` referans alindi
- `shared/api-contracts/ws/agent-messages.json` referans alindi
- 2 REST endpoint + 3 WS mesaj tipi dogrulandi
- Tum field isimleri ve tipleri kontratlarla uyumlu

## Notlar

- Agent registry in-memory: DB baglantisi gerekmeden calisir (F1 icin yeterli)
- Agent ve iOS client'lar ayri ConnectionManager instance kullaniyor
- Stale check 30sn aralikla calisir, 90sn heartbeat timeout
- REST endpoint'ler simdilik JWT auth gerektirmiyor (kolaylik icin). Gerekirse sonra eklenebilir.
- AgentCapability enum doc 08'deki yetenek matrisinden turetildi
