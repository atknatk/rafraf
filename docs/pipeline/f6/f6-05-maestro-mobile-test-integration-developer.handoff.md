# Developer Handoff: Maestro Mobile Test Integration

**Issue**: #41
**Branch**: feature/f6/41-f6-05-maestro-mobile-test-integra
**Tarih**: 2026-03-03
**Sonraki Agent**: tester (standard pipeline)

## Yapilan Degisiklikler

| Dosya | Islem | Aciklama |
|-------|-------|----------|
| `apps/backend/app/schemas/maestro.py` | CREATE | Maestro test request/response Pydantic schemalar |
| `apps/backend/app/services/maestro_service.py` | CREATE | Maestro test orkestrasyonu ve sonuc isleme servisi |
| `apps/backend/app/api/routes/maestro.py` | CREATE | REST endpoint'leri (run-flow, run-suite, validate, screenshot, list-flows, report) |
| `apps/backend/app/main.py` | MODIFY | Maestro router kaydi eklendi |
| `apps/agent/agent/testing/mobile/__init__.py` | CREATE | Mobile testing modulu init |
| `apps/agent/agent/testing/mobile/models.py` | CREATE | Maestro flow/suite/sonuc modelleri (frozen Pydantic v2) |
| `apps/agent/agent/testing/mobile/orchestrator.py` | CREATE | MaestroRunner uzerinden flow/suite orkestratoru |
| `apps/agent/agent/testing/mobile/reporter.py` | CREATE | JSON/text rapor olusturucu + S3 upload |

## Mimari Kararlar

- **Backend service layer**: MaestroService runner sonuclarini isler, agent dispatch placeholder olarak tutuldu (gercek WS dispatch ayri issue'da yapilacak)
- **Agent orchestrator**: MaestroTestOrchestrator, MaestroRunner uzerinden flow ve suite calistirma yonetir
- **Frozen modeller**: Tum domain modelleri frozen Pydantic v2 kullanir (immutable)
- **CI rapor formati**: MaestroTestReport modeli screenshot'li adim bazli rapor icin kullanilir
- **Stop on failure**: Suite calistirmada opsiyonel, varsayilan olarak tum flow'lar calisir
- **Platform destegi**: iOS ve Android destegi (MaestroPlatform enum)

## Dogrulama Sonuclari

| Arac | Durum | Detay |
|------|-------|-------|
| ruff check | PASS | Backend (3 dosya) + Agent (4 dosya) hatasiz |
| ruff format | PASS | Formatlama uyumlu |
| mypy | PASS | Backend (3 dosya) + Agent (4 dosya) strict mode hatasiz |

## API Kontrat Uyumu

Bu feature icin shared/api-contracts/ altinda kontrat dosyasi bulunmuyor. Maestro test endpoint'leri internal agent dispatch icin kullanilir ve iOS client tarafindan dogrudan cagrilmaz.

## Notlar

- Backend route'lari agent dispatch placeholder kullanir (agent WS baglantisi yapildiginda gercek runner cagrilacak)
- Agent mobile testing modulu, mevcut testing framework'u (Playwright) ile paralel calisir
- MaestroReporter, TestReporter ile ayni pattern'i takip eder (JSON + text + S3)
- Tester icin: backend schemas, service, route + agent models, orchestrator, reporter icin unit testler yazilmali
