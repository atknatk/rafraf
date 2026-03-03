# Architect Handoff: Auth Flow (JWT + Keychain + Biometric)

**Issue**: #26
**Faz**: F4
**Tarih**: 2026-03-03
**Sonraki Agent**: developer

## Ozet

iOS kimlik dogrulama akisi. Backend JWT auth endpoint'leri (`/api/v1/auth/token`, `/api/v1/auth/refresh`) zaten mevcut (F1-02'de implemente edildi). Bu feature tamamen iOS tarafinda calisir: login/register ekranlari, Keychain'de guvenli token saklama, token auto-refresh, biyometrik dogrulama (Face ID / Touch ID), auth state yonetimi.

## Feature Spec

-> `shared/feature-specs/f4-26-f4-03-auth-flow-jwt-keychain-biometric.md`

## API Contracts

-> `shared/api-contracts/rest/v1/auth.json` (MEVCUT — yeni endpoint yok)

Mevcut endpoint'ler:
- `POST /api/v1/auth/token` — Login ve JWT token olusturma
- `POST /api/v1/auth/refresh` — Refresh token ile yeni token pair alma

## Katman Dagilimi

| Katman | Oncelik | Tahmini Dosya Sayisi |
|--------|---------|---------------------|
| ios | HIGH | ~20 dosya |
| backend | N/A | 0 dosya (mevcut) |
| agent | N/A | 0 dosya |

## Dikkat Edilecekler

- **Backend API mevcut**: `apps/backend/app/api/routes/auth.py`, `apps/backend/app/services/auth_service.py`, `apps/backend/app/core/security.py` dosyalari zaten implemente. Developer agent backend kodu YAZMAMALI.
- **Keychain guvenlik**: Token'lar `kSecClassGenericPassword` ile saklanmali. `UserDefaults` kullanimini KESINLIKLE YASAK.
- **NetworkClient mevcut**: `apps/ios/RafRaf/Core/Networking/NetworkClient.swift` actor pattern ile mevcut. Auth interceptor entegrasyonu icin `buildRequest` metoduna token injection eklenmeli.
- **Factory DI mevcut**: `apps/ios/RafRaf/Core/DI/AppContainer.swift` dosyasi mevcut. Yeni auth servisleri buraya eklenmeli.
- **RF* componentler zorunlu**: Login/register ekranlarinda `RFButton`, `RFTextField`, `RFText` vb. kullanilmali. Raw SwiftUI `Button`, `Text`, `TextField` YASAK.
- **Mevcut RF* componentler**: RFButton, RFCard, RFText, RFTextField, RFAvatar, RFEmptyStateView, RFErrorView, RFLoadingView mevcut.
- **ContentView**: Auth gate eklenmeli — AuthManager state'ine gore login veya main tab bar gosterilmeli.
- **snake_case <-> camelCase**: NetworkClient'ta `keyDecodingStrategy = .convertFromSnakeCase` mevcut. DTO field isimleri Swift convention'a (camelCase) uygun olmali.

## Dogrulama

- [x] Feature spec yazildi
- [x] API kontratlar mevcut (yeni endpoint yok)
- [x] Dosya sahipligi belirlendi
- [x] Doc referanslari kontrol edildi (docs/04_iOS_App_Specification.md)
