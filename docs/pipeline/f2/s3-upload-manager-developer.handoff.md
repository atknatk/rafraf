# Developer Handoff: S3 Upload Manager

**Issue**: #18
**Branch**: feature/f2/18-s3-upload-manager
**Tarih**: 2026-03-02
**Sonraki Agent**: tester

## Yapilan Degisiklikler

| Dosya | Islem | Aciklama |
|-------|-------|----------|
| `apps/agent/agent/upload/s3_uploader.py` | MODIFY | aioboto3 async, multipart upload, pre-signed URL, progress callback, retry, dosya dogrulama eklendi |
| `apps/agent/agent/upload/__init__.py` | MODIFY | Modul docstring eklendi |
| `apps/agent/pyproject.toml` | MODIFY | boto3 -> aioboto3, boto3-stubs -> types-aiobotocore[s3] |
| `apps/agent/agent/runners/playwright_runner.py` | MODIFY | upload_bytes donus tipini UploadResult.url'e guncellendi |
| `apps/agent/agent/runners/maestro_runner.py` | MODIFY | upload_bytes donus tipini UploadResult.url'e guncellendi |
| `apps/agent/tests/unit/test_upload/test_s3_uploader.py` | MODIFY | Yeni API'ye uygun smoke testler yazildi |
| `apps/agent/tests/unit/test_runners/test_maestro_runner.py` | MODIFY | Mock UploadResult dondurmeye guncellendi |
| `apps/agent/tests/unit/test_runners/test_playwright_runner.py` | MODIFY | Mock UploadResult dondurmeye guncellendi |

## Dogrulama Sonuclari

| Arac | Durum | Detay |
|------|-------|-------|
| ruff check | PASS | All checks passed |
| mypy | PASS | No issues found in 20 source files |
| pytest | PASS | 452 passed in ~66s |

## Yeni Ozellikler

1. **aioboto3 async client**: Senkron boto3 + run_in_executor yerine native async aioboto3
2. **Multipart upload**: 10MB esik degeri, otomatik parca bolme
3. **Pre-signed URL**: GET ve PUT icin pre-signed URL olusturma
4. **Progress callback**: UploadProgress dataclass ile ilerleme raporlama
5. **Retry mekanizmasi**: Exponential backoff ile yapilandirmali retry
6. **Dosya dogrulama**: Tip (uzanti) ve boyut (100MB maks) dogrulama
7. **Dosya upload**: Path tabanli dosya yukleme (validate_file + upload)
8. **Helper fonksiyonlar**: detect_content_type, build_s3_key

## API Kontrat Uyumu

Bu issue agent katmaninda calisiyor ve REST/WS API endpoint'i icermiyor. Kontrat dogrulama gerekmiyor.

## Notlar

- Mevcut S3Uploader tamamen yeniden yazildi (sync boto3 -> async aioboto3)
- Constructor degisti: `S3Uploader(bucket, region, client)` -> `S3Uploader(config=S3Config(...), client=...)`
- `upload_bytes` artik `str` yerine `UploadResult` dondurur
- PlaywrightRunner ve MaestroRunner guncellendi (`.url` erisimi)
- Tum mevcut testler guncellendi ve gecti
- Tester agent icin: Multipart upload edge case'leri, progress callback detayli testleri, retry senaryolari ve dosya dogrulama edge case'leri yazilmali
