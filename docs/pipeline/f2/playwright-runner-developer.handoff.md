# Developer Handoff: Playwright Runner (Screenshot, Page Load)

**Issue**: #15
**Branch**: feature/f2/15-playwright-runner
**Tarih**: 2026-03-02
**Sonraki Agent**: tester

## Yapilan Degisiklikler

| Dosya | Islem | Aciklama |
|-------|-------|----------|
| `apps/agent/agent/runners/playwright_runner.py` | CREATE | Playwright runner - screenshot, page load, element check, form fill, network response |
| `apps/agent/agent/upload/__init__.py` | CREATE | Upload modulu init |
| `apps/agent/agent/upload/s3_uploader.py` | CREATE | S3 byte upload yardimcisi |
| `apps/agent/pyproject.toml` | MODIFY | boto3 ve boto3-stubs dependency eklendi |

## Dogrulama Sonuclari

| Arac | Durum | Detay |
|------|-------|-------|
| ruff check | PASS | Tum kontroller gecti |
| mypy | PASS | Strict mode, 15 dosya kontrol edildi |

## Aksiyonlar ve Parametreler

| Action | Parametreler | Aciklama |
|--------|-------------|----------|
| take_screenshot | url, full_page?, selector?, viewport_width?, viewport_height? | Sayfa/element screenshot |
| check_page_load | url, wait_until?, timeout? | Sayfa yukleme kontrolu |
| check_element | url, selector, timeout? | Element varlik kontrolu |
| fill_form | url, fields[], submit_selector? | Form doldurma |
| wait_for_response | url, url_pattern, timeout? | Network response bekleme |

## API Kontrat Uyumu

Bu feature yeni API kontrat gerektirmez. Mevcut agent_command WS mesaj akisi uzerinden
tetiklenir. Kontrat degisikligi yoktur.

## Notlar

- BaseRunner pattern'i takip edildi (DockerRunner ile tutarli)
- Playwright async API kullanildi (sync API yok)
- Browser her islemde acilip kapatiliyor (izolasyon)
- S3 upload basarisiz olursa base64 fallback mevcut
- Tum domain/entity modeller Pydantic frozen=True
- structlog ile loglama yapildi
- mypy strict mode gecti
- boto3 dependency eklendi (S3 upload icin)
- types-boto3 (boto3-stubs) dev dependency eklendi (mypy icin)
