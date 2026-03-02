# Architect Handoff: Agent Daemon Base (WSS, Heartbeat, Reconnect)

**Issue**: #13
**Faz**: F2
**Tarih**: 2026-03-02
**Sonraki Agent**: developer

## Ozet

Host Agent daemon temel yapisi. asyncio tabanli Python daemon, backend'e WSS ile baglanir, heartbeat gonderir, kopmalarda exponential backoff ile yeniden baglanir. Graceful shutdown destekler. Capability reporting ile agent'in destekledigi runner'lari backend'e bildirir.

## Feature Spec

-> `shared/feature-specs/f2-13-f2-01-agent-daemon-base-wss-heartbeat.md`

## API Contracts

-> `shared/api-contracts/ws/agent-messages.json` (mevcut - agent_register, agent_register_ack, agent_heartbeat)

Yeni REST endpoint veya WS mesaj tipi gerekmiyor. Mevcut kontratlar kullanilacak.

## Katman Dagilimi

| Katman | Oncelik | Tahmini Dosya Sayisi |
|--------|---------|---------------------|
| agent | HIGH | 5 dosya |
| backend | N/A | 0 dosya (mevcut altyapi yeterli) |
| ios | N/A | 0 dosya |

## Dikkat Edilecekler

- `websockets` kutuphanesi kullanilmali (agent pyproject.toml'da mevcut)
- Reconnect stratejisi: 1s -> 2s -> 4s -> 8s -> 16s -> 32s -> max 60s (issue'da belirtilen)
- Heartbeat interval: varsayilan 30sn, backend'ten `agent_register_ack` ile override edilebilir
- Auth: `X-API-Key` header ile WSS baglantisi
- Signal handling: `SIGTERM` ve `SIGINT` icin graceful shutdown
- `structlog` ile structured JSON logging zorunlu
- Pydantic domain modelleri `frozen=True` olmali
- AgentConfig icin `pydantic-settings` kullanilmali (env vars'dan okuma)
- `psutil` ile sistem metrikleri toplanmali (heartbeat'te gonderilir)
- Mevcut `shared/api-contracts/ws/agent-messages.json` kontratina tam uyum saglanmali
- `agent/__init__.py`, `agent/core/__init__.py`, `agent/monitoring/__init__.py` bos dosyalar zaten mevcut

## Dogrulama

- [x] Feature spec yazildi
- [x] API kontratlar mevcut (shared/api-contracts/ws/agent-messages.json)
- [x] Dosya sahipligi belirlendi
- [x] Doc referanslari kontrol edildi (docs/08_Host_Agent_Specification.md)
