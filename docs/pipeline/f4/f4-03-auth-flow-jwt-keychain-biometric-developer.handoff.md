# Developer Handoff: Auth Flow (JWT + Keychain + Biometric)

**Issue**: #26
**Branch**: feature/f4/26-f4-03-auth-flow-jwt-keychain-biometric
**Tarih**: 2026-03-03
**Sonraki Agent**: tester

## Yapilan Degisiklikler

| Dosya | Islem | Aciklama |
|-------|-------|----------|
| `apps/ios/RafRaf/Core/Auth/KeychainHelper.swift` | CREATE | Keychain CRUD islemleri (save, read, delete) |
| `apps/ios/RafRaf/Core/Auth/BiometricAuthManager.swift` | CREATE | Face ID / Touch ID dogrulama |
| `apps/ios/RafRaf/Core/Auth/AuthManager.swift` | CREATE | JWT state yonetimi, auto-refresh, token CRUD |
| `apps/ios/RafRaf/Core/Auth/AuthInterceptor.swift` | CREATE | NetworkClient Authorization header enjeksiyonu |
| `apps/ios/RafRaf/Features/Auth/Data/DTOs/AuthDTOs.swift` | CREATE | TokenRequestDTO, RefreshRequestDTO, TokenResponseDTO |
| `apps/ios/RafRaf/Features/Auth/Data/Mappers/AuthMapper.swift` | CREATE | DTO -> AuthToken domain model donusumu |
| `apps/ios/RafRaf/Features/Auth/Data/Repositories/AuthRepositoryImpl.swift` | CREATE | Auth API cagrilari (login, refreshToken) |
| `apps/ios/RafRaf/Features/Auth/Domain/Models/AuthModels.swift` | CREATE | AuthToken domain modeli |
| `apps/ios/RafRaf/Features/Auth/Domain/Repositories/AuthRepository.swift` | CREATE | AuthRepositoryProtocol |
| `apps/ios/RafRaf/Features/Auth/Domain/UseCases/LoginUseCase.swift` | CREATE | Login is mantigi |
| `apps/ios/RafRaf/Features/Auth/Domain/UseCases/LogoutUseCase.swift` | CREATE | Logout (token temizleme) |
| `apps/ios/RafRaf/Features/Auth/Domain/UseCases/RefreshTokenUseCase.swift` | CREATE | Token yenileme |
| `apps/ios/RafRaf/Features/Auth/Domain/UseCases/BiometricLoginUseCase.swift` | CREATE | Biyometrik dogrulama ile giris |
| `apps/ios/RafRaf/Features/Auth/Presentation/Views/RFLoginView.swift` | CREATE | Login ekrani (RF* componentler) |
| `apps/ios/RafRaf/Features/Auth/Presentation/Views/RFRegisterView.swift` | CREATE | Register ekrani (RF* componentler) |
| `apps/ios/RafRaf/Features/Auth/Presentation/ViewModels/AuthViewModel.swift` | CREATE | Auth presentation logic |
| `apps/ios/RafRaf/Features/Auth/Presentation/Components/RFBiometricButton.swift` | CREATE | Biyometrik buton (Face ID/Touch ID) |
| `apps/ios/RafRaf/App/ContentView.swift` | MODIFY | Auth gate eklendi |
| `apps/ios/RafRaf/Core/DI/AppContainer.swift` | MODIFY | Auth DI kayitlari |
| `apps/ios/RafRaf/Core/Networking/NetworkClient.swift` | MODIFY | AuthInterceptor entegrasyonu |

## API Kontrat Uyumu

- **Referans dosya**: `shared/api-contracts/rest/v1/auth.json`
- **Dogrulanan endpoint sayisi**: 2
- `POST /api/v1/auth/token` — Login (TokenRequestDTO -> TokenResponseDTO)
- `POST /api/v1/auth/refresh` — Refresh (RefreshRequestDTO -> TokenResponseDTO)
- NetworkClient baseURL `/api/v1` icerdiginden path'ler `/auth/token` ve `/auth/refresh` olarak kullanildi
- snake_case <-> camelCase: `keyDecodingStrategy = .convertFromSnakeCase` mevcut, DTO'lar camelCase

## Dogrulama Sonuclari

| Arac | Durum | Detay |
|------|-------|-------|
| swiftlint | SKIPPED | CI'da calisacak |
| xcodebuild build | SKIPPED | CI'da calisacak |
| xcodebuild test | SKIPPED | Tester agent yazacak |

## Notlar

- Backend kodu degistirilmedi — mevcut JWT auth endpoint'leri kullanildi
- Token'lar `kSecAttrAccessibleWhenUnlockedThisDeviceOnly` ile korunuyor
- Auto-refresh: token suresinin dolmasina 60sn kala schedule edilir
- Biyometrik tercih Keychain'de `auth_biometric_enabled` anahtari ile saklanir
- `#Preview` bloklari login ve register ekranlarinda mevcut
- Tum kullanici-gorunur stringler `String(localized:)` ile tanimli
- RF* componentler kullanildi (RFButton, RFTextField, RFText, RFCard, RFLoadingView)
