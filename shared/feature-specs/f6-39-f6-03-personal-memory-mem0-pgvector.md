# Feature: Personal Memory (mem0 + pgvector, fact extraction)

**Issue**: #39
**Faz**: F6
**Katmanlar**: backend
**Pipeline**: full
**Tarih**: 2026-03-03

## Ozet

Kisisel hafiza sistemi. mem0 + pgvector ile kullanici tercihlerini ve aliskanliklarini ogrenme.
Kullanicinin kisisel tercihlerini, calisma tarzini ve gecmis kararlari saklayarak AI'in
kullaniciyi "tanimasi"ni saglar. Oturum sonunda konusmalardan otomatik fact extraction yapar,
kullanici profili olusturur/gunceller ve gizlilik kontrolleri sunar.

## Mevcut Durum

Onceki fazlarda (F6-01 conversation memory, F6-02 project memory) MemoryService sinifinda
temel mem0 entegrasyonu zaten mevcut:
- `_get_mem0()`: Lazy mem0 client initialization
- `save_conversation_facts()`: Oturum sonu fact extraction (mem0.add)
- `search_memories()`: Semantic search (mem0.search)
- `delete_personal_memory()`: Tekil hafiza silme (mem0.delete)
- `get_all_personal_memories()`: Tum hafizalari listele (mem0.get_all)
- REST endpoints: GET/DELETE `/api/v1/memory/personal/{user_id}`

## Bu Feature ile Eklenecekler

1. **Kullanici profil olusturma/guncelleme** - Kullanicinin tercih ve aliskanliklarini yapisal profil olarak saklama
2. **Gelismis fact extraction** - Konusmalardan kisisel tercihleri otomatik cikarma (mem0'nun yaninda backend-side extraction)
3. **Gizlilik kontrolleri** - Kullanicinin tum kisisel hafizasini toplu silme (right to be forgotten)
4. **Hafiza guncelleme** - Mevcut hafizayi guncelleme endpoint'i (mem0.update)
5. **Personal memory istatistikleri** - Kullanicinin hafiza sayisi, kategorileri

## Degisecek Dosyalar

### Backend (`apps/backend/`)

| Dosya | Islem | Aciklama |
|-------|-------|----------|
| `app/services/personal_memory_service.py` | CREATE | Kisisel hafiza business logic (profil, fact extraction, gizlilik) |
| `app/schemas/personal_memory.py` | CREATE | Request/response schema'lari (profil, update, stats, bulk delete) |
| `app/api/routes/personal_memory.py` | CREATE | Yeni REST endpoint'ler (profil, update, stats, bulk delete) |
| `app/api/routes/__init__.py` | MODIFY | Yeni router kaydi |
| `app/services/memory_service.py` | MODIFY | update_personal_memory metodu ekleme |

## API Endpoints

### REST

| Method | Path | Request | Response | Aciklama |
|--------|------|---------|----------|----------|
| GET | `/api/v1/personal-memory/{user_id}/profile` | - | `UserProfileResponse` | Kullanici profili (tercihler, aliskanliklar) |
| PUT | `/api/v1/personal-memory/{user_id}/profile` | `UserProfileUpdateRequest` | `UserProfileResponse` | Kullanici profilini guncelle |
| POST | `/api/v1/personal-memory/{user_id}/extract` | `PersonalFactExtractionRequest` | `PersonalFactExtractionResponse` | Konusmadan kisisel fact extraction |
| PUT | `/api/v1/personal-memory/{user_id}/memories/{memory_id}` | `PersonalMemoryUpdateRequest` | `PersonalMemoryItem` | Tekil hafiza guncelle |
| DELETE | `/api/v1/personal-memory/{user_id}/all` | - | `BulkDeleteResponse` | Tum kisisel hafizalari sil (gizlilik) |
| GET | `/api/v1/personal-memory/{user_id}/stats` | - | `PersonalMemoryStatsResponse` | Hafiza istatistikleri |

## Data Model

### mem0 (pgvector) - Var Olan

mem0 tablosu mem0 tarafindan otomatik olusturulur. Ek tablo GEREKMEZ.
`user_id` bazli filtreleme mem0 SDK uzerinden yapilir.

### Pydantic Models

```python
class UserProfile(BaseModel):
    model_config = ConfigDict(frozen=True)

    user_id: str
    preferences: dict[str, object]
    habits: list[str]
    total_memories: int
    last_updated: datetime | None


class PersonalFactExtractionRequest(BaseModel):
    messages: list[dict[str, str]] = Field(min_length=1)


class PersonalFactExtractionResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    extracted_memories: list[str]
    total: int


class PersonalMemoryUpdateRequest(BaseModel):
    data: str = Field(min_length=1, max_length=4096)


class BulkDeleteResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    deleted_count: int
    user_id: str


class PersonalMemoryStatsResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    user_id: str
    total_memories: int
    oldest_memory_date: datetime | None
    newest_memory_date: datetime | None
```

## Business Rules

1. Kullanici profili mem0'daki tum hafizalardan dinamik olarak olusturulur (ayri tablo yok)
2. Profil preference'lari hafizalardan analiz edilerek cikarilir
3. Fact extraction Claude Haiku ile yapilir (maliyet optimizasyonu)
4. Bulk delete geri donusumsuz - kullanici uyarilmali (frontend sorumlulugu)
5. Memory update mem0.update kullanir - mevcut hafizanin icerigini degistirir
6. Stats endpoint mem0.get_all uzerinden hesaplanir
7. Tum islemler user_id bazli izole - baska kullanicinin hafizasina erisim YASAK

## Test Requirements

### Backend
- [ ] Unit test: PersonalMemoryService profil olusturma (mock mem0)
- [ ] Unit test: PersonalMemoryService fact extraction (mock Claude API)
- [ ] Unit test: PersonalMemoryService bulk delete (mock mem0)
- [ ] Unit test: PersonalMemoryService memory update (mock mem0)
- [ ] Unit test: PersonalMemoryService stats hesaplama (mock mem0)
- [ ] Integration test: POST /personal-memory/{user_id}/extract endpoint
- [ ] Integration test: PUT /personal-memory/{user_id}/memories/{memory_id} endpoint
- [ ] Integration test: DELETE /personal-memory/{user_id}/all endpoint
- [ ] Integration test: GET /personal-memory/{user_id}/profile endpoint
- [ ] Integration test: GET /personal-memory/{user_id}/stats endpoint

## Acceptance Criteria

- [ ] mem0 entegrasyonu (personal scope) - mevcut, genisletilecek
- [ ] pgvector ile semantic search - mevcut
- [ ] Otomatik fact extraction (kullanici tercihlerini cikart)
- [ ] Kullanici profil olusturma/guncelleme
- [ ] Hafiza sorgulama (benzer bilesenler bul) - mevcut
- [ ] Gizlilik kontrolleri (kullanici silme isteyebilir)
- [ ] Unit + integration testler yazildi
- [ ] Coverage >= 80%
