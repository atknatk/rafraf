# Architect Handoff: Playwright Runner (Screenshot, Page Load)

**Issue**: #15
**Faz**: F2
**Tarih**: 2026-03-02
**Sonraki Agent**: developer

## Ozet

Playwright async API ile web sayfasi islemleri yapan runner. Screenshot alma,
sayfa yukleme kontrolu, element varlik dogrulama, form doldurma ve network
response bekleme yeteneklerini iceren BaseRunner turevli sinif.

## Feature Spec

-> `shared/feature-specs/f2-15-playwright-runner.md`

## API Contracts

Bu feature yeni API kontrat gerektirmez. Mevcut `agent_command` WS mesaj akisi
uzerinden tetiklenir. Kontrat degisikligi yoktur.

## Katman Dagilimi

| Katman | Oncelik | Tahmini Dosya Sayisi |
|--------|---------|---------------------|
| agent | HIGH | 3 dosya |
| backend | N/A | 0 dosya |
| ios | N/A | 0 dosya |

## Dikkat Edilecekler

- Mevcut `BaseRunner` soyut sinifini kullan (agent/runners/base.py)
- `DockerRunner` pattern'ini takip et (agent/runners/docker_runner.py)
- Playwright async API kullan (sync API YASAK)
- Browser instance her islemde yeni acilip kapatilmali (kaynak sizintisi onleme)
- S3 uploader ayri module olarak olusturulmali (diger runner'lar da kullanabilir)
- `boto3` S3 client kullanilacak (pyproject.toml'da `boto3` dependency var mi kontrol et, yoksa ekle)
- Timeout handling: page.goto timeout, asyncio.wait_for timeout, vb.
- Screenshot PNG formati zorunlu
- structlog ile loglama zorunlu
- Pydantic frozen=True domain/entity modeller icin

## Dogrulama

- [x] Feature spec yazildi
- [x] API kontratlar olusturuldu (degisiklik yok)
- [x] Dosya sahipligi belirlendi
- [x] Doc referanslari kontrol edildi (docs/08_Host_Agent_Specification.md)
