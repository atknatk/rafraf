# Feature: JWT Authentication System

**Issue**: #8
**Faz**: F1
**Katmanlar**: backend
**Pipeline**: full
**Tarih**: 2026-03-02

## Ozet

JWT tabanli kimlik dogrulama sistemi. iOS uygulamasi icin access ve refresh token olusturma, dogrulama ve yenileme mekanizmasi. Bu feature, tum API endpoint'lerini ve WebSocket baglantilerini guvenli hale getirir. Rate limiting middleware ile brute-force saldirilarina karsi koruma saglar.

## Degisecek Dosyalar

### Backend (`apps/backend/`)
| Dosya | Islem | Aciklama |
|-------|-------|----------|
| `app/models/user.py` | CREATE | User SQLAlchemy model (UUID pk, email, hashed_password, is_active, timestamps) |
| `app/schemas/auth.py` | CREATE | Auth request/response Pydantic schemas (TokenRequest, TokenResponse, RefreshRequest, UserResponse) |
| `app/repositories/user_repository.py` | CREATE | User DB erisim katmani (get_by_email, get_by_id, create) |
| `app/services/auth_service.py` | CREATE | Auth business logic (authenticate, create_tokens, refresh_token) |
| `app/api/routes/auth.py` | CREATE | Auth REST endpoint'leri (POST /api/v1/auth/token, POST /api/v1/auth/refresh) |
| `app/api/middleware/rate_limit.py` | CREATE | Rate limiting middleware (Redis tabanli, IP bazli) |
| `app/core/security.py` | MODIFY | Refresh token support, password hashing, token blacklist |
| `app/core/config.py` | MODIFY | Refresh token suresi, rate limit ayarlari eklenmesi |
| `app/api/deps.py` | MODIFY | get_current_user dependency eklenmesi |
| `app/main.py` | MODIFY | Auth router ve rate limit middleware eklenmesi |
| `alembic/versions/<hash>_add_users_table.py` | CREATE | User tablosu migration |

## API Endpoints

### REST
| Method | Path | Request | Response | Aciklama |
|--------|------|---------|----------|----------|
| POST | `/api/v1/auth/token` | `TokenRequest` (email, password) | `TokenResponse` (access_token, refresh_token, token_type, expires_in) | Login ve token olusturma |
| POST | `/api/v1/auth/refresh` | `RefreshRequest` (refresh_token) | `TokenResponse` (access_token, refresh_token, token_type, expires_in) | Token yenileme |

### WebSocket Messages
Mevcut WebSocket baglanti akisi korunur. Token query parameter uzerinden dogrulanir (mevcut `/ws?token=` yapisi).

## Data Model

### PostgreSQL
```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) NOT NULL UNIQUE,
    hashed_password VARCHAR(255) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_users_email ON users (email);
```

### Pydantic Models

```python
# schemas/auth.py - Request/Response DTO'lar (frozen KULLANILMAZ)
class TokenRequest(BaseModel):
    email: str
    password: str

class RefreshRequest(BaseModel):
    refresh_token: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int

class UserResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    email: str
    is_active: bool
    created_at: str
```

### Token Payload
```json
{
  "sub": "<user_id_uuid>",
  "type": "access|refresh",
  "iat": 1709312400,
  "exp": 1709313300
}
```

## Business Rules

1. **Access token suresi**: 15 dakika (issue'da belirtilen)
2. **Refresh token suresi**: 7 gun (issue'da belirtilen)
3. **Algoritma**: HS256 (docs/07 referansi)
4. **Password hashing**: bcrypt (passlib)
5. **Token blacklist**: Refresh token kullanildiginda eski refresh token Redis'te blacklist'e eklenir (token rotation)
6. **Rate limiting**: Auth endpoint'lerinde IP bazli rate limit (10 istek/dakika)
7. **WebSocket auth**: Mevcut query parameter tabanli JWT dogrulama korunur
8. **Token response**: Her token response'da hem access hem refresh token dondurulur
9. **Expired refresh token**: 401 Unauthorized dondurulur, client yeniden login yapmali

## Test Requirements

### Backend
- [ ] Unit test: create_access_token dogru payload olusturur
- [ ] Unit test: create_refresh_token dogru payload olusturur
- [ ] Unit test: verify_access_token gecerli token'i dogrular
- [ ] Unit test: verify_access_token expired token'i reddeder
- [ ] Unit test: verify_refresh_token gecerli token'i dogrular
- [ ] Unit test: password_hash ve verify dogru calisir
- [ ] Unit test: TokenRequest validation (bos email, bos password)
- [ ] Integration test: POST /api/v1/auth/token basarili login
- [ ] Integration test: POST /api/v1/auth/token yanlis credentials
- [ ] Integration test: POST /api/v1/auth/refresh basarili yenileme
- [ ] Integration test: POST /api/v1/auth/refresh expired refresh token
- [ ] Integration test: Rate limiting 429 response
- [ ] Integration test: WebSocket authentication token ile baglanti

## Acceptance Criteria

- [ ] JWT token olusturma (access + refresh)
- [ ] Token dogrulama middleware
- [ ] Token yenileme endpoint'i
- [ ] Rate limiting middleware
- [ ] WebSocket authentication (token ile baglanti)
- [ ] User model + DB migration
- [ ] Unit + integration testler yazildi
- [ ] Coverage >= 80%
