# Developer Handoff: S3 File Manager Tool

**Issue**: #21
**Branch**: feature/f3/21-f3-02-s3-file-manager-tool
**Tarih**: 2026-03-02
**Sonraki Agent**: tester

## Yapilan Degisiklikler

| Dosya | Islem | Aciklama |
|-------|-------|----------|
| `apps/backend/app/services/s3_service.py` | CREATE | S3 async service - aioboto3 ile dosya islemleri |
| `apps/backend/app/tools/s3_tool.py` | CREATE | Claude tool - 6 action (upload, download, list, delete, presigned URLs) |
| `apps/backend/app/core/config.py` | MODIFY | aws_region config eklendi |
| `apps/backend/pyproject.toml` | MODIFY | aioboto3 dependency ve mypy overrides eklendi |

## Implementasyon Detaylari

### S3Service (`app/services/s3_service.py`)
- **aioboto3** async session management
- `upload_file`: Dosya yukleme (100MB limit)
- `download_file`: Dosya indirme
- `list_files`: Prefix bazli dosya listeleme
- `delete_file`: Dosya silme
- `generate_presigned_upload_url`: PUT pre-signed URL (varsayilan 1 saat)
- `generate_presigned_download_url`: GET pre-signed URL (varsayilan 1 saat)
- Bucket yapisi: `projects/{project_id}/...`
- Custom exception: `S3ServiceError`

### S3Tool (`app/tools/s3_tool.py`)
- Tool name: `s3_file_manager`
- 6 action: upload_file, download_file, list_files, delete_file, generate_presigned_upload_url, generate_presigned_download_url
- Per-action approval: upload_file ve delete_file onay gerektirir
- Base64 encoding/decoding for file content transfer
- Input validation for required parameters

## Dogrulama Sonuclari

| Arac | Durum | Detay |
|------|-------|-------|
| ruff check | PASS | Tum dosyalar temiz |
| mypy | PASS | 50 dosya, 0 hata |

## API Kontrat Uyumu

Bu feature bir Claude tool oldugu icin REST API kontrati bulunmuyor. Tool schema `_S3_TOOL_SCHEMA` olarak tanimli.

## Notlar

- aioboto3 session her islemde `async with session.client("s3")` pattern ile kullanilir
- Dosya icerigi Base64 ile encode/decode edilir (Claude tool sinirlamalari nedeniyle)
- Pre-signed URL'ler iOS client'in dogrudan S3'e upload/download yapmasini saglar
- Approval sistemi per-action bazinda calisiyor (upload ve delete icin)
