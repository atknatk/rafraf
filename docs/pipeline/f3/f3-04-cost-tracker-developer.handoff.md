# Developer Handoff: Cost Tracker

**Issue**: #23
**Branch**: feature/f3/23-f3-04-cost-tracker
**Tarih**: 2026-03-02
**Sonraki Agent**: tester (standard pipeline)

## Yapilan Degisiklikler

| Dosya | Islem | Aciklama |
|-------|-------|----------|
| `apps/backend/app/models/cost_log.py` | CREATE | CostLog SQLAlchemy modeli - token kullanimi ve maliyet kaydi |
| `apps/backend/app/models/__init__.py` | MODIFY | CostLog model import eklendi |
| `apps/backend/app/schemas/cost.py` | CREATE | Pydantic request/response semalari - entity, DTO, rapor modelleri |
| `apps/backend/app/schemas/__init__.py` | MODIFY | Cost schema importlari eklendi |
| `apps/backend/app/repositories/cost_repository.py` | CREATE | CostRepository - CRUD + aggregation sorgulari |
| `apps/backend/app/services/cost_service.py` | CREATE | CostService - maliyet hesaplama, raporlama, budget kontrolu |
| `apps/backend/app/api/routes/cost.py` | CREATE | REST endpointleri - log, report, users, budget, models |
| `apps/backend/app/tools/cost_tool.py` | CREATE | Claude AI tool - maliyet takibi tool tanimlari |
| `apps/backend/app/main.py` | MODIFY | Cost router eklendi |
| `apps/backend/alembic/versions/002_add_cost_logs_table.py` | CREATE | cost_logs tablo migration |

## Kabul Kriterleri Durumu

- [x] Token kullanimi kaydetme (input + output)
- [x] Model bazli maliyet hesaplama (Opus, Sonnet, Haiku fiyatlandirmasi)
- [x] Gunluk/aylik toplam raporlama
- [x] Budget limit/alert sistemi
- [x] Kullanici bazli maliyet takibi
- [x] Tool tanimlari (Claude tool schema)
- [ ] Unit testler yazildi (tester agent'in isi)
- [ ] Coverage >= 80% (tester agent'in isi)

## Dogrulama Sonuclari

| Arac | Durum | Detay |
|------|-------|-------|
| ruff check | PASS | 0 hata |
| mypy | PASS | 63 dosya kontrol edildi, 0 hata |

## API Kontrat Uyumu

Bu feature icin henuz `shared/api-contracts/rest/v1/` altinda bir kontrat dosyasi mevcut degil. Endpointler issue body'sindeki kabul kriterlerine gore tasarlandi.

## Endpointler

| Method | Path | Aciklama |
|--------|------|----------|
| POST | `/api/v1/cost/log` | Yeni maliyet kaydi olustur |
| GET | `/api/v1/cost/logs/{user_id}` | Kullanici maliyet loglarini listele |
| GET | `/api/v1/cost/report` | Gunluk/aylik rapor olustur |
| GET | `/api/v1/cost/users` | Kullanici bazli ozet |
| GET | `/api/v1/cost/budget` | Budget durum kontrolu |
| GET | `/api/v1/cost/models` | Desteklenen modeller ve fiyatlandirma |

## Model Fiyatlandirmasi

| Model | Input (1M token) | Output (1M token) |
|-------|-------------------|--------------------|
| claude-opus-4-5-20250929 | $15.00 | $75.00 |
| claude-sonnet-4-5-20250929 | $3.00 | $15.00 |
| claude-haiku-4-5-20251001 | $0.80 | $4.00 |

## Notlar

- PostgreSQL `cost_logs` tablosu user_id, model, called_at alanlarinda indexed
- Maliyet hesaplama model bazli fiyat tablosundan otomatik yapilir
- Budget alert sistemi gunluk ve aylik limitler icin log-based kontrol yapar
- CostTool, Claude AI tool registry'ye kaydedilir (orchestrator tarafindan cagrilir)
- Bilinmeyen modeller icin fallback fiyatlandirma (Sonnet fiyati) uygulanir
