# Architect Handoff: Project Memory (PostgreSQL, Auto-Update)

**Issue**: #38
**Faz**: F6
**Tarih**: 2026-03-03
**Sonraki Agent**: developer

## Ozet

Proje hafizasi sistemi gelistirmesi. Mevcut ProjectMemory modeli ve basit CRUD
endpoint'leri uzerine otomatik fact extraction, arama/filtreleme, proje ozeti
ve stale kayit temizleme yetenekleri eklenmektedir. Backend-only feature.

## Feature Spec

-> `shared/feature-specs/f6-38-f6-02-project-memory-postgresql-auto.md`

## API Contracts

-> `shared/api-contracts/rest/v1/memory.json` (4 yeni endpoint eklendi)

## Katman Dagilimi

| Katman | Oncelik | Tahmini Dosya Sayisi |
|--------|---------|---------------------|
| backend | HIGH | 5 dosya |
| ios | N/A | 0 dosya |
| agent | N/A | 0 dosya |

## Dikkat Edilecekler

- Mevcut `memory.py` model, repository, service ve route dosyalari MODIFY edilecek
- Yeni `project_memory_service.py` service dosyasi olusturulacak (fact extraction logic)
- `last_verified_at` alani `Text` -> `DateTime(timezone=True)` olarak degistirilmeli
- Alembic migration olusturulmali
- Fact extraction icin Claude Haiku API cagrisi gerekiyor - mock edilmeli testlerde
- `docs/05_Memory_System_Specification.md` referans alinmali
- mem0 bagimliligi (F3-03) onceden tamamlanmis

## Dogrulama

- [x] Feature spec yazildi
- [x] API kontratlar olusturuldu (4 yeni endpoint)
- [x] Dosya sahipligi belirlendi
- [x] Doc referanslari kontrol edildi
