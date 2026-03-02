# Architect Handoff: Memory Manager (mem0 + 3-Layer)

**Issue**: #22
**Faz**: F3
**Tarih**: 2026-03-02
**Sonraki Agent**: developer

## Ozet

mem0 ile 3-katmanli hafiza sistemi. Conversation (Redis, kisa sureli), Project (PostgreSQL, orta sureli) ve Personal (mem0+pgvector, uzun sureli) hafiza yonetimi. Backend-only feature, cloud tool olarak calisir.

## Feature Spec

-> `shared/feature-specs/f3-22-f3-03-memory-manager-mem0-3-layer.md`

## API Contracts

-> `shared/api-contracts/rest/v1/memory.json`

## Katman Dagilimi

| Katman | Oncelik | Tahmini Dosya Sayisi |
|--------|---------|---------------------|
| backend | HIGH | 12 dosya |
| ios | N/A | 0 dosya |
| agent | N/A | 0 dosya |

## Dikkat Edilecekler

- mem0 `Memory.from_config()` ile baslatilir. Config icinde pgvector (vector_store), openai embedder ve anthropic llm tanimlanir.
- Conversation memory Redis'te saklanir. Session bazli TTL uygulanir.
- Project memory PostgreSQL'de `project_memory` tablosunda, UPSERT semantigi ile (project_id + category + key unique constraint).
- Personal memory mem0+pgvector ile semantic search. Similarity threshold >= 0.60.
- Token butcesi: personal=1500, project=1000, conversation_summary=500 token max.
- `memory_manager` Claude cloud tool olarak tanimlanir (BaseTool'dan turetilir).
- Referans: `docs/05_Memory_System_Specification.md` ve `docs/03_AI_Agent_Tool_Layer_Specification.md`
- Bagimlilk: F1-03 (Claude AI Orchestrator) — zaten implement edilmis.
- Yeni Python dependency: `mem0ai`, `redis[hiredis]`

## Dogrulama

- [x] Feature spec yazildi
- [x] API kontratlar olusturuldu
- [x] Dosya sahipligi belirlendi
- [x] Doc referanslari kontrol edildi
