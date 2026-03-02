# Architect Handoff: Host Agent Registry + Health Monitoring

**Issue**: #10
**Faz**: F1
**Tarih**: 2026-03-02
**Sonraki Agent**: developer

## Ozet

Host Agent'larin backend'e WebSocket uzerinden kaydolmasi, heartbeat ile saglik takibi ve REST API uzerinden agent durumlarinin sorgulanmasi sistemi. Backend tarafinda agent registry servisi, agent WebSocket endpoint'i ve REST endpoint'leri olusturulacak.

## Feature Spec

-> `shared/feature-specs/f1-10-host-agent-registry-health-monitoring.md`

## API Contracts

-> `shared/api-contracts/rest/v1/agents.json`
-> `shared/api-contracts/ws/agent-messages.json`

## Katman Dagilimi

| Katman | Oncelik | Tahmini Dosya Sayisi |
|--------|---------|---------------------|
| backend | HIGH | 7 dosya (5 CREATE + 2 MODIFY) |
| ios | N/A | 0 dosya |
| agent | N/A | 0 dosya |

## Dikkat Edilecekler

- Agent WebSocket endpoint `/ws/agent` uzerinden calisir (iOS client `/ws` endpoint'inden ayri)
- Agent auth API key ile olur (JWT degil). Config'deki `agent_api_key` ile dogrulanir
- `host_agents` tablosu SQLAlchemy modeli olarak olusturulacak (Alembic migration optional, CI'da DB olmadigi icin)
- Stale agent detection icin lifespan'a asyncio background task eklenmeli (90sn heartbeat timeout)
- Agent registry servisi in-memory cache + DB hybrid: hizli erisim icin in-memory dict, kalicilik icin DB (su an DB baglantisiniz yok, tamamen in-memory calisabilir)
- REST endpoint'ler JWT auth ile korunmali
- MessageType enum'a yeni agent mesaj tipleri eklenmeli

## Dogrulama

- [x] Feature spec yazildi
- [x] API kontratlar olusturuldu
- [x] Dosya sahipligi belirlendi
- [x] Doc referanslari kontrol edildi (08_Host_Agent_Specification.md)
