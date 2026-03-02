# Developer Handoff: Agent Daemon Base (WSS, Heartbeat, Reconnect)

**Issue**: #13
**Branch**: feature/f2/13-agent-daemon-base-wss-heartbeat
**Tarih**: 2026-03-02
**Sonraki Agent**: tester

## Yapilan Degisiklikler

| Dosya | Islem | Aciklama |
|-------|-------|----------|
| `apps/agent/agent/core/config.py` | CREATE | Pydantic Settings ile agent konfigurasyonu |
| `apps/agent/agent/core/connection.py` | CREATE | WSS baglanti yonetimi (connect, reconnect, heartbeat) |
| `apps/agent/agent/core/protocol.py` | CREATE | Mesaj protokolu (register, heartbeat, parse) |
| `apps/agent/agent/monitoring/metrics.py` | CREATE | psutil ile sistem metrik toplama |
| `apps/agent/agent/main.py` | MODIFY | Daemon entry point - signal handling, graceful shutdown |

## API Kontrat Uyumu

- Referans kontrat: `shared/api-contracts/ws/agent-messages.json`
- Dogrulanan mesaj tipleri: 3 (agent_register, agent_register_ack, agent_heartbeat)
- Tum mesaj field'lari ve tipleri kontrat ile uyumlu

## Dogrulama Sonuclari

| Arac | Durum | Detay |
|------|-------|-------|
| ruff check | PASS | Tum kontroller gecti |
| mypy | PASS | Strict mode, 10 dosya kontrol edildi |
| pytest | PENDING | Tester agent yazacak |

## Notlar

- `websockets` v14+ async client API kullanildi (`websockets.asyncio.client.ClientConnection`)
- Exponential backoff: 1s -> 2s -> 4s -> ... -> max 60s (config'dan ayarlanabilir)
- Heartbeat interval: varsayilan 30s, backend'ten `agent_register_ack` ile override edilebilir
- Signal handling: SIGTERM + SIGINT icin graceful shutdown
- psutil blocking cagrilari `asyncio.run_in_executor` ile thread pool'da calistiriliyor
- Domain modelleri (ResourceMetrics, RegisterContent, vb.) frozen=True
- AgentConfig: pydantic-settings ile env vars'dan okunur (AGENT_ prefix)
