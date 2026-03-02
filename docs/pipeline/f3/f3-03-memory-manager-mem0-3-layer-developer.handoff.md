# Developer Handoff: Memory Manager (mem0 + 3-Layer)

**Issue**: #22
**Branch**: feature/f3/22-f3-03-memory-manager-mem0-3-layer
**Tarih**: 2026-03-02
**Sonraki Agent**: tester

## Yapilan Degisiklikler

| Dosya | Islem | Aciklama |
|-------|-------|----------|
| `apps/backend/app/models/memory.py` | CREATE | ProjectMemory SQLAlchemy modeli (UPSERT, JSONB, unique constraint) |
| `apps/backend/app/schemas/memory.py` | CREATE | Pydantic request/response semalari (entity, DTO, context) |
| `apps/backend/app/repositories/memory_repository.py` | CREATE | ProjectMemory DB repository (list, upsert, delete, summary) |
| `apps/backend/app/services/memory_service.py` | CREATE | 3-katmanli hafiza servisi (conversation, project, personal + context builder) |
| `apps/backend/app/tools/memory_tool.py` | CREATE | Claude memory_manager tool (7 action) |
| `apps/backend/app/api/routes/memory.py` | CREATE | REST API endpoint'leri (6 endpoint) |
| `apps/backend/app/core/redis.py` | CREATE | Redis client wrapper (conversation cache, generic cache) |
| `apps/backend/app/main.py` | MODIFY | Memory router ve redis shutdown eklendi |
| `apps/backend/app/models/__init__.py` | MODIFY | ProjectMemory import |
| `apps/backend/app/schemas/__init__.py` | MODIFY | Memory semalari import |
| `apps/backend/pyproject.toml` | MODIFY | mem0ai dependency + mypy override |

## Dogrulama Sonuclari

| Arac | Durum | Detay |
|------|-------|-------|
| ruff check | PASS | 0 error, 0 warning |
| ruff format | PASS | Tum dosyalar formatli |
| mypy | PASS | 0 error (strict mode) |

## API Kontrat Uyumu

- Referans: `shared/api-contracts/rest/v1/memory.json`
- 6 endpoint dogrulandi (GET/POST/DELETE project, GET/DELETE personal, GET context)
- Path, method, query params, request/response body tamamen kontrata uyumlu

## Notlar

- mem0 client lazy-initialized (ilk kullanima kadar baslatilamaz, test icin mock gerekir)
- Redis client module-level singleton, lifespan'da close edilir
- ProjectMemory modeli PostgreSQL UPSERT icin `on_conflict_do_update` kullanir
- Token budget: personal=1500, project=1000, conversation_summary=500
- Similarity threshold: 0.60 (altindaki sonuclar filtrelenir)
- mem0 sync API kullanilir (mem0 kutuphanesi async desteklemiyor, blocking cagri)
- Tester agent icin: mem0 mock edilmeli (dis API), Redis ve PostgreSQL gercek test DB ile calistirilmali
