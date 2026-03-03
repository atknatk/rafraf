# Developer Handoff: Project Memory (PostgreSQL, Auto-Update)

**Issue**: #38
**Branch**: feature/f6/38-f6-02-project-memory-postgresql-auto
**Tarih**: 2026-03-03
**Sonraki Agent**: tester

## Yapilan Degisiklikler

| Dosya | Islem | Aciklama |
|-------|-------|----------|
| `app/models/memory.py` | MODIFY | last_verified_at Text -> DateTime(timezone=True) |
| `app/repositories/memory_repository.py` | MODIFY | search, stale detection, count, batch delete, verify, grouped listing |
| `app/schemas/memory.py` | MODIFY | ExtractedFact, FactExtractionRequest/Response, ProjectSummaryResponse, StaleCleanupResponse |
| `app/services/project_memory_service.py` | CREATE | Otomatik fact extraction (Claude Haiku), arama, ozet, stale temizlik |
| `app/api/routes/memory.py` | MODIFY | 4 yeni endpoint: /search, /summary, /extract, /stale |

## Dogrulama Sonuclari

| Arac | Durum | Detay |
|------|-------|-------|
| ruff check | PASS | All checks passed |
| ruff format | PASS | All files formatted |
| mypy | PASS | No issues found in 5 source files |

## API Kontrat Uyumu

- Referans: `shared/api-contracts/rest/v1/memory.json`
- 4 yeni endpoint eklendi: search, summary, extract, stale
- Tum endpoint path'leri, method'lari ve parametre isimleri kontrat ile uyumlu
- Response schema'lari kontrat ile eslesiyor

## Notlar

- Claude Haiku API cagrisi fact extraction icin kullaniliyor - testlerde mock edilmeli
- `last_verified_at` alani artik `DateTime(timezone=True)` tipinde (onceden Text idi)
- UPSERT isleminde `last_verified_at` otomatik guncelleniyor
- Stale entries: `last_verified_at` NULL olan veya 30+ gun eski olan kayitlar
- Arama: key uzerinde ILIKE + JSONB value uzerinde text cast + ILIKE
