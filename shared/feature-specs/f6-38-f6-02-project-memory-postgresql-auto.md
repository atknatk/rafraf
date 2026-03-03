# Feature: Project Memory (PostgreSQL, Auto-Update)

**Issue**: #38
**Faz**: F6
**Katmanlar**: backend
**Pipeline**: full
**Tarih**: 2026-03-03

## Ozet

Proje hafizasi sistemi, PostgreSQL ile kalici proje bilgisi saklama ve konusmalardan
otomatik bilgi cikarma (fact extraction) yetenegini saglar. Konusma sirasinda
projeye ait teknik bilgiler, durum degisiklikleri ve tercihler otomatik olarak
algilanip veritabanina kaydedilir. Bu sayede AI her yeni konusmada projenin
guncel durumunu bilir.

## Degisecek Dosyalar

### Backend (`apps/backend/`)
| Dosya | Islem | Aciklama |
|-------|-------|----------|
| `app/models/memory.py` | MODIFY | ProjectMemory modeline last_verified_at DateTime tipi eklenmesi |
| `app/repositories/memory_repository.py` | MODIFY | Stale entry tespiti, arama/filtreleme, toplu guncelleme |
| `app/services/project_memory_service.py` | CREATE | Otomatik fact extraction, proje durumu takibi, tercih yonetimi |
| `app/schemas/memory.py` | MODIFY | Yeni request/response schemalar (search, stale, batch update) |
| `app/api/routes/memory.py` | MODIFY | Yeni endpoint'ler (search, summary, stale cleanup) |

## API Endpoints

### REST
| Method | Path | Request | Response | Aciklama |
|--------|------|---------|----------|----------|
| GET | `/api/v1/memory/project/{project_id}` | `?category&key` | `ProjectMemoryListResponse` | Mevcut - filtreli listeleme |
| POST | `/api/v1/memory/project/{project_id}` | `ProjectMemoryCreateRequest` | `ProjectMemoryResponse` | Mevcut - UPSERT |
| DELETE | `/api/v1/memory/project/{project_id}/{memory_id}` | - | 204 | Mevcut - silme |
| GET | `/api/v1/memory/project/{project_id}/search` | `?q&category&min_confidence` | `ProjectMemoryListResponse` | YENi - arama/filtreleme |
| GET | `/api/v1/memory/project/{project_id}/summary` | - | `ProjectSummaryResponse` | YENi - proje ozeti |
| POST | `/api/v1/memory/project/{project_id}/extract` | `FactExtractionRequest` | `FactExtractionResponse` | YENi - otomatik fact extraction |
| DELETE | `/api/v1/memory/project/{project_id}/stale` | `?days_threshold` | `StaleCleanupResponse` | YENi - stale kayitlari temizle |

## Data Model

### PostgreSQL
Mevcut `project_memory` tablosu kullanilir. `last_verified_at` alaninin tip duzeltmesi:

```sql
-- last_verified_at Text -> TIMESTAMPTZ olarak duzeltilecek
ALTER TABLE project_memory
  ALTER COLUMN last_verified_at TYPE TIMESTAMPTZ USING last_verified_at::TIMESTAMPTZ;
```

### Pydantic Models

```python
class ProjectMemorySearchRequest(BaseModel):
    """Arama/filtreleme parametreleri."""
    q: str | None = None
    category: str | None = None
    min_confidence: float = Field(default=0.0, ge=0.0, le=1.0)

class FactExtractionRequest(BaseModel):
    """Otomatik fact extraction istegi."""
    messages: list[dict[str, str]]
    source: str = "ai_inferred"

class FactExtractionResponse(BaseModel):
    """Otomatik fact extraction sonucu."""
    model_config = ConfigDict(frozen=True)
    extracted_facts: list[ExtractedFact]
    total: int

class ExtractedFact(BaseModel):
    """Tek bir cikarilmis bilgi."""
    model_config = ConfigDict(frozen=True)
    category: str
    key: str
    value: dict[str, object]
    confidence: float

class ProjectSummaryResponse(BaseModel):
    """Proje hafiza ozeti."""
    model_config = ConfigDict(frozen=True)
    project_id: str
    categories: dict[str, list[ProjectMemoryResponse]]
    total_memories: int
    stale_count: int

class StaleCleanupResponse(BaseModel):
    """Stale temizlik sonucu."""
    model_config = ConfigDict(frozen=True)
    deleted_count: int
    threshold_days: int
```

## Business Rules

1. `project_memory` tablosunda `(project_id, category, key)` unique constraint ile UPSERT destegi
2. Otomatik fact extraction Claude Haiku ile konusma analizi yapar ve yapisal bilgiler cikarir
3. Cikarilan bilgilerin `confidence` degeri, AI cikarimi icin 0.7, kullanici ifadesi icin 1.0, tool sonucu icin 0.9
4. `last_verified_at` 30 gunden eski kayitlar "stale" olarak isaretlenir
5. Stale temizlik endpointi sadece belirli esik gunden eski kayitlari siler
6. Arama hem JSONB value icinde hem de category/key uzerinde yapilir
7. Kategori tipleri: `tech_stack`, `known_issues`, `deployment`, `architecture_decisions`, `preferences`, `status`

## Test Requirements

### Backend
- [ ] Unit test: ProjectMemoryService fact extraction
- [ ] Unit test: Stale detection logic
- [ ] Unit test: Search/filter logic
- [ ] Integration test: UPSERT endpoint
- [ ] Integration test: Search endpoint
- [ ] Integration test: Stale cleanup endpoint
- [ ] Integration test: Fact extraction endpoint

## Acceptance Criteria

- [ ] Project memory DB modeli dogru calisir
- [ ] Otomatik bilgi cikarma (konusmadan proje bilgisi) uygulanmis
- [ ] Proje durumu takibi calisiyor
- [ ] Proje tercihleri saklama calisiyor
- [ ] Arama/filtreleme calisiyor
- [ ] Stale kayitlar tespit ve temizleniyor
- [ ] Unit + integration testler yazildi
- [ ] Coverage >= 80%
