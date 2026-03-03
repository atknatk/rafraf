# Architect Handoff: Project Status Cards

**Issue**: #32
**Faz**: F5
**Tarih**: 2026-03-03
**Sonraki Agent**: developer

## Ozet

Proje durumunu gosteren kart componentleri ozelliginin teknik spesifikasyonu. Backend'de REST endpoint'ler, iOS'ta Clean Architecture ile liste ve detay ekranlari.

## Feature Spec

-> `shared/feature-specs/f5-32-project-status-cards.md`

## API Contracts

-> `shared/api-contracts/rest/v1/projects.json`

## Katman Dagilimi

| Katman | Oncelik | Tahmini Dosya Sayisi |
|--------|---------|---------------------|
| backend | HIGH | 6 dosya |
| ios | HIGH | 13 dosya |
| agent | N/A | 0 dosya |

## Dikkat Edilecekler

- Backend'de `Project` modeli henuz yok, sifirdan olusturulacak
- `app/schemas/projects.py` ve `app/models/project.py` dosyalari spec'te zaten planliydi ama henuz eklenmemis
- iOS'ta `RFProjectCard` yeni bir RF* component olarak olusturulacak
- Mevcut `RFCard` componenti temel alinabilir
- Pull-to-refresh icin `.refreshable` modifier kullanilmali
- `LazyVStack` ile performansli liste (Chat feature'daki pattern ile ayni)
- Domain layer'da Foundation disinda import YASAK

## Dogrulama

- [x] Feature spec yazildi
- [x] API kontratlar olusturuldu
- [x] Dosya sahipligi belirlendi
- [x] Doc referanslari kontrol edildi
