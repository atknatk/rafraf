# Architect Handoff: Personal Memory (mem0 + pgvector, fact extraction)

**Issue**: #39
**Faz**: F6
**Tarih**: 2026-03-03
**Sonraki Agent**: developer

## Ozet

Kisisel hafiza sistemi genisletmesi. Mevcut mem0 entegrasyonunun uzerine kullanici profili,
gelismis fact extraction, hafiza guncelleme, gizlilik kontrolleri (bulk delete) ve istatistik
endpoint'leri ekleniyor. Sadece backend katmanini etkiler.

## Feature Spec

-> `shared/feature-specs/f6-39-f6-03-personal-memory-mem0-pgvector.md`

## API Contracts

-> `shared/api-contracts/rest/v1/personal-memory.json`

## Katman Dagilimi

| Katman | Oncelik | Tahmini Dosya Sayisi |
|--------|---------|---------------------|
| backend | HIGH | 5 dosya |
| ios | N/A | 0 dosya |
| agent | N/A | 0 dosya |

## Mevcut Kod Durumu

Asagidaki dosyalar zaten mevcut ve calisiyor:
- `app/services/memory_service.py`: MemoryService sinifi (Layer 3: personal memory temel islemleri)
- `app/schemas/memory.py`: PersonalMemoryItem, MemoryContext vs.
- `app/api/routes/memory.py`: GET/DELETE personal memory endpoint'leri
- `app/repositories/memory_repository.py`: ProjectMemory icin (personal memory mem0 uzerinden)

Bu feature **yeni dosyalar** olusturarak mevcut yapiya ek fonksiyonellik katar:
- `app/services/personal_memory_service.py` (YENi) - Profil, fact extraction, bulk delete, stats
- `app/schemas/personal_memory.py` (YENI) - Yeni request/response tipleri
- `app/api/routes/personal_memory.py` (YENI) - Yeni endpoint'ler
- `app/services/memory_service.py` (MODIFY) - update_personal_memory metodu ekleme
- `app/api/routes/__init__.py` (MODIFY) - Router kaydi

## Dikkat Edilecekler

- mem0 SDK sync calisiyor, async wrapper kullanilmali veya threadpool ile calistirilmali
- Mevcut `_get_mem0()` lazy initialization patternini kullan
- `PersonalMemoryItem` zaten `app/schemas/memory.py`'da tanimli, tekrar tanimlama
- Fact extraction icin Claude Haiku kullan (maliyet optimizasyonu)
- Gizlilik: bulk delete islemi geri donusumsuz
- user_id bazli izolasyon: her islem sadece o user'in hafizasina erismeli
- `structlog` ile loglama zorunlu
- `Any` tipi YASAK

## Dogrulama

- [x] Feature spec yazildi
- [x] API kontratlar olusturuldu
- [x] Dosya sahipligi belirlendi
- [x] Doc referanslari kontrol edildi (docs/05_Memory_System_Specification.md)
