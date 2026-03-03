# Feature: Auth Flow (JWT + Keychain + Biometric)

**Issue**: #26
**Faz**: F4
**Katmanlar**: ios
**Pipeline**: full
**Tarih**: 2026-03-03

## Ozet

iOS kimlik dogrulama akisi. Backend'de mevcut JWT auth endpoint'leri (`/api/v1/auth/token`, `/api/v1/auth/refresh`) ile entegre olur. Kullanici login/register ekranlarindan kimligini dogrular, JWT token'lari Keychain'de guvenli saklanir, token suresi dolunca auto-refresh yapilir, biyometrik dogrulama (Face ID / Touch ID) ile hizli giris desteklenir. Auth state `@Observable` pattern ile tum uygulamaya yayilir.

## Degisecek Dosyalar

### iOS (`apps/ios/`)

| Dosya | Islem | Aciklama |
|-------|-------|----------|
| `RafRaf/Core/Auth/KeychainHelper.swift` | CREATE | Keychain CRUD islemleri |
| `RafRaf/Core/Auth/BiometricAuthManager.swift` | CREATE | Face ID / Touch ID dogrulama |
| `RafRaf/Core/Auth/AuthManager.swift` | CREATE | JWT state yonetimi, auto-refresh, logout |
| `RafRaf/Core/Auth/AuthInterceptor.swift` | CREATE | NetworkClient token enjeksiyonu |
| `RafRaf/Features/Auth/Data/DTOs/AuthDTOs.swift` | CREATE | TokenRequest, RefreshRequest, TokenResponse DTO |
| `RafRaf/Features/Auth/Data/Repositories/AuthRepositoryImpl.swift` | CREATE | Auth API cagrilari |
| `RafRaf/Features/Auth/Data/Mappers/AuthMapper.swift` | CREATE | DTO -> Domain model donusumleri |
| `RafRaf/Features/Auth/Domain/Models/AuthModels.swift` | CREATE | AuthToken, AuthState domain modelleri |
| `RafRaf/Features/Auth/Domain/Repositories/AuthRepository.swift` | CREATE | Auth repository protocol |
| `RafRaf/Features/Auth/Domain/UseCases/LoginUseCase.swift` | CREATE | Login is mantigi |
| `RafRaf/Features/Auth/Domain/UseCases/LogoutUseCase.swift` | CREATE | Logout is mantigi |
| `RafRaf/Features/Auth/Domain/UseCases/RefreshTokenUseCase.swift` | CREATE | Token yenileme is mantigi |
| `RafRaf/Features/Auth/Domain/UseCases/BiometricLoginUseCase.swift` | CREATE | Biyometrik giris is mantigi |
| `RafRaf/Features/Auth/Presentation/Views/RFLoginView.swift` | CREATE | Login ekrani |
| `RafRaf/Features/Auth/Presentation/Views/RFRegisterView.swift` | CREATE | Register ekrani |
| `RafRaf/Features/Auth/Presentation/ViewModels/AuthViewModel.swift` | CREATE | Auth presentation logic |
| `RafRaf/Features/Auth/Presentation/Components/RFBiometricButton.swift` | CREATE | Biyometrik giris butonu |
| `RafRaf/Core/DI/AppContainer.swift` | MODIFY | Auth DI kayitlari |
| `RafRaf/Core/Networking/NetworkClient.swift` | MODIFY | Auth interceptor entegrasyonu |
| `RafRaf/App/ContentView.swift` | MODIFY | Auth gate (login vs main tab) |

## API Endpoints

### REST

Backend'de mevcut endpoint'ler kullanilir. Yeni endpoint EKLENMEZ.

| Method | Path | Request | Response | Aciklama |
|--------|------|---------|----------|----------|
| POST | `/api/v1/auth/token` | `TokenRequest` | `TokenResponse` | Login (mevcut) |
| POST | `/api/v1/auth/refresh` | `RefreshRequest` | `TokenResponse` | Token yenileme (mevcut) |

### WebSocket Messages

Yeni WS mesaji YOK. Auth token WebSocket handshake'de query param olarak gonderilir (mevcut altyapi).

## Data Model

### Pydantic Models (Mevcut - Degisiklik Yok)

```python
# apps/backend/app/schemas/auth.py — MEVCUT
class TokenRequest(BaseModel):
    email: EmailStr
    password: str

class RefreshRequest(BaseModel):
    refresh_token: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
```

### Swift Models

```swift
// Domain/Models/AuthModels.swift
struct AuthToken: Sendable {
    let accessToken: String
    let refreshToken: String
    let tokenType: String
    let expiresIn: Int
    let expiresAt: Date
}

enum AuthState: Sendable {
    case unknown
    case authenticated(AuthToken)
    case unauthenticated
}

// Data/DTOs/AuthDTOs.swift
struct TokenRequestDTO: Codable, Sendable {
    let email: String
    let password: String
}

struct RefreshRequestDTO: Codable, Sendable {
    let refreshToken: String
}

struct TokenResponseDTO: Codable, Sendable {
    let accessToken: String
    let refreshToken: String
    let tokenType: String
    let expiresIn: Int
}
```

## Business Rules

1. **Login akisi**: Email + password -> backend `/auth/token` -> JWT pair -> Keychain'e kaydet -> AuthState = authenticated
2. **Auto-refresh**: Access token suresi dolmadan 60sn once refresh endpoint'i cagrilir. Basarisizsa unauthenticated state'e gec.
3. **Auto-login**: Uygulama acilisinda Keychain'den token oku -> expire olmamissa authenticated state, expire ise refresh dene, basarisizsa login ekranina yonlendir.
4. **Biyometrik**: Kullanici tercihi ile Face ID / Touch ID aktif edebilir. Biyometrik basariliysa Keychain'den token okunur.
5. **Logout**: Access + refresh token Keychain'den silinir, AuthState = unauthenticated, login ekranina don.
6. **Token Keychain'de saklanir**: UserDefaults'a JWT token YAZILMAZ. Keychain `kSecClassGenericPassword` ile saklanir.
7. **Auth gate**: ContentView, AuthManager'in state'ine gore login ekrani veya ana tab bar gosterir.
8. **Token injection**: NetworkClient her istege `Authorization: Bearer <token>` header'i ekler. 401 gelirse auto-refresh dener.

## Test Requirements

### iOS
- [ ] Unit test: KeychainHelper CRUD islemleri
- [ ] Unit test: AuthManager state gecisleri (unknown -> authenticated -> unauthenticated)
- [ ] Unit test: AuthViewModel login/logout/register akislari
- [ ] Unit test: BiometricAuthManager availability check
- [ ] Unit test: LoginUseCase basari/hata senaryolari
- [ ] Unit test: LogoutUseCase token temizleme
- [ ] Unit test: RefreshTokenUseCase basari/hata
- [ ] Unit test: AuthMapper DTO -> Domain donusumleri
- [ ] Unit test: AuthInterceptor token injection
- [ ] Contract test: iOS API URL'leri ve method'lari kontrat ile eslesiyor mu

## Acceptance Criteria

- [ ] Login ekrani email + password ile giris yapar
- [ ] Register ekrani yeni kullanici olusturur
- [ ] JWT token Keychain'de guvenli saklanir (UserDefaults YASAK)
- [ ] Token suresi dolunca auto-refresh yapilir
- [ ] Biyometrik dogrulama (Face ID / Touch ID) desteklenir
- [ ] Auth state @Observable ile yonetilir
- [ ] Uygulama acilisinda Keychain'den auto-login dener
- [ ] Logout islemi token'lari temizler ve login ekranina yonlendirir
- [ ] NetworkClient 401 alinca auto-refresh dener
- [ ] Tum stringler localized
- [ ] Tum view'larda #Preview var
- [ ] RF* componentler kullanildi (raw SwiftUI YASAK)
- [ ] Coverage >= 70%
