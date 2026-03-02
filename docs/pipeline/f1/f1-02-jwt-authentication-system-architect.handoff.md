# Architect Handoff: JWT Authentication System

**Issue**: #8
**Faz**: F1
**Tarih**: 2026-03-02
**Sonraki Agent**: developer

## Ozet

JWT tabanli kimlik dogrulama sistemi. Access token (15dk) ve refresh token (7 gun) ile token olusturma, dogrulama ve yenileme. Rate limiting middleware ile brute-force korunmasi. User model ve DB migration dahil.

## Feature Spec

-> `shared/feature-specs/f1-8-f1-02-jwt-authentication-system.md`

## API Contracts

-> `shared/api-contracts/rest/v1/auth.json`

## Katman Dagilimi

| Katman | Oncelik | Tahmini Dosya Sayisi |
|--------|---------|---------------------|
| backend | HIGH | 11 dosya |
| ios | N/A | 0 dosya |
| agent | N/A | 0 dosya |

## Dikkat Edilecekler

- Mevcut `app/core/security.py` dosyasinda zaten `create_access_token` ve `verify_access_token` var. Bunlari refresh token destegi ile genislet.
- `app/core/config.py` dosyasinda `jwt_access_token_expire_minutes` zaten tanimli (30dk). Issue'da 15dk belirtilmis, bunu guncelle.
- Refresh token suresi icin `jwt_refresh_token_expire_days: int = 7` ekle.
- Rate limit icin Redis kullanilmali. Config'e `rate_limit_requests_per_minute: int = 10` ekle.
- Password hashing icin `passlib[bcrypt]` zaten dependency'lerde mevcut.
- Token payload'inda `type` field'i ile access ve refresh token ayrimi yap.
- WebSocket auth mevcut haliyle korunur (query parameter ile token dogrulama).
- Alembic migration olusturmayi unutma.
- `get_current_user` dependency'si tum korunmasi gereken endpoint'ler icin kullanilacak.

## Dogrulama

- [x] Feature spec yazildi
- [x] API kontratlar olusturuldu
- [x] Dosya sahipligi belirlendi
- [x] Doc referanslari kontrol edildi (docs/02, docs/07)
