# Feature: Push Notifications (APNs)

**Issue**: #36
**Faz**: F5
**Katmanlar**: backend | ios
**Pipeline**: full
**Tarih**: 2026-03-03

## Ozet

Push bildirim sistemi, kullanicilara uygulama disindayken onemli olaylari bildirir. APNs (Apple Push Notification service) entegrasyonu ile iOS cihazlara bildirim gonderilir. Bildirim tipleri (task_complete, approval_needed, error, info) ile farkli onem seviyelerinde bildirimler desteklenir. Deep linking ile bildirime tiklandiginda ilgili ekrana yonlendirme yapilir.

## Degisecek Dosyalar

### Backend (`apps/backend/`)
| Dosya | Islem | Aciklama |
|-------|-------|----------|
| `app/api/routes/notifications.py` | CREATE | Push notification REST endpoint'leri (token kaydi, bildirim gonderme) |
| `app/schemas/notifications.py` | CREATE | Pydantic request/response modelleri |
| `app/services/notification_service.py` | CREATE | APNs bildirim gonderme servisi |
| `app/models/device_token.py` | CREATE | Device token SQLAlchemy modeli |
| `app/repositories/device_token_repo.py` | CREATE | Device token DB erisim katmani |
| `app/main.py` | MODIFY | Notification router eklenmesi |

### iOS (`apps/ios/`)
| Dosya | Islem | Aciklama |
|-------|-------|----------|
| `RafRaf/Core/Notifications/PushNotificationManager.swift` | CREATE | APNs token yonetimi ve bildirim handling |
| `RafRaf/Core/Notifications/NotificationRouter.swift` | CREATE | Deep linking - bildirim payload'dan ekrana yonlendirme |
| `RafRaf/Features/Notifications/Data/DTOs/DeviceTokenDTO.swift` | CREATE | Device token kayit DTO |
| `RafRaf/Features/Notifications/Data/DTOs/NotificationPayloadDTO.swift` | CREATE | Gelen bildirim payload DTO |
| `RafRaf/Features/Notifications/Data/Repositories/NotificationRepositoryImpl.swift` | CREATE | Bildirim repository implementasyonu |
| `RafRaf/Features/Notifications/Data/Mappers/NotificationMapper.swift` | CREATE | DTO -> Domain model mapper |
| `RafRaf/Features/Notifications/Domain/Models/PushNotification.swift` | CREATE | Bildirim domain modeli |
| `RafRaf/Features/Notifications/Domain/Models/NotificationCategory.swift` | CREATE | Bildirim kategorileri enum |
| `RafRaf/Features/Notifications/Domain/Repositories/NotificationRepositoryProtocol.swift` | CREATE | Repository protocol |
| `RafRaf/Features/Notifications/Domain/UseCases/RegisterDeviceTokenUseCase.swift` | CREATE | Token kayit use case |
| `RafRaf/Features/Notifications/Domain/UseCases/HandleNotificationUseCase.swift` | CREATE | Bildirim isleme use case |
| `RafRaf/Features/Notifications/Presentation/ViewModels/NotificationSettingsViewModel.swift` | CREATE | Bildirim ayarlari ViewModel |
| `RafRaf/Features/Notifications/Presentation/Views/NotificationSettingsView.swift` | CREATE | Bildirim ayarlari ekrani |
| `RafRaf/Features/Notifications/Presentation/Components/RFNotificationBanner.swift` | CREATE | In-app bildirim banner bilesei |
| `RafRaf/App/RafRafApp.swift` | MODIFY | AppDelegate eklenmesi (push notification lifecycle) |
| `RafRaf/App/AppDelegate.swift` | CREATE | UNUserNotificationCenter delegate |
| `RafRaf/Core/DI/AppContainer.swift` | MODIFY | Notification DI kayitlari |

## API Endpoints

### REST
| Method | Path | Request | Response | Aciklama |
|--------|------|---------|----------|----------|
| POST | `/api/v1/notifications/device-token` | `DeviceTokenRegisterRequest` | `DeviceTokenRegisterResponse` | APNs device token kaydi |
| DELETE | `/api/v1/notifications/device-token` | `DeviceTokenDeleteRequest` | `204 No Content` | Token silme (logout) |
| GET | `/api/v1/notifications/settings` | - | `NotificationSettingsResponse` | Bildirim ayarlarini getir |
| PATCH | `/api/v1/notifications/settings` | `NotificationSettingsUpdateRequest` | `NotificationSettingsResponse` | Bildirim ayarlarini guncelle |

### WebSocket Messages
| Direction | Type | Payload | Aciklama |
|-----------|------|---------|----------|
| server->client | `notification` | `NotificationPayload` | Yeni bildirim geldi (in-app gosterim icin) |

## Data Model

### PostgreSQL
```sql
CREATE TABLE device_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token TEXT NOT NULL,
    platform TEXT NOT NULL DEFAULT 'ios',
    app_version TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, token)
);

CREATE TABLE notification_settings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    task_complete_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    approval_needed_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    error_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    info_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### Pydantic Models
```python
from pydantic import BaseModel, ConfigDict, Field
from uuid import UUID
from datetime import datetime
from enum import Enum


class NotificationType(str, Enum):
    task_complete = "task_complete"
    approval_needed = "approval_needed"
    error = "error"
    info = "info"


class DeviceTokenRegisterRequest(BaseModel):
    token: str = Field(..., min_length=1, max_length=512, description="APNs device token")
    platform: str = Field(default="ios", description="Platform (ios)")
    app_version: str | None = Field(default=None, description="Uygulama versiyonu")


class DeviceTokenRegisterResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    registered_at: datetime


class DeviceTokenDeleteRequest(BaseModel):
    token: str = Field(..., min_length=1, max_length=512, description="Silinecek APNs device token")


class NotificationSettingsResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    task_complete_enabled: bool
    approval_needed_enabled: bool
    error_enabled: bool
    info_enabled: bool


class NotificationSettingsUpdateRequest(BaseModel):
    task_complete_enabled: bool | None = None
    approval_needed_enabled: bool | None = None
    error_enabled: bool | None = None
    info_enabled: bool | None = None


class NotificationPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    notification_id: UUID
    type: NotificationType
    title: str
    body: str
    deep_link: str | None = None
    badge_count: int = 0
    metadata: dict[str, str] = Field(default_factory=dict)
```

### Swift Models
```swift
/// Bildirim kategorisi.
enum NotificationCategory: String, Sendable, CaseIterable {
    case taskComplete = "task_complete"
    case approvalNeeded = "approval_needed"
    case error = "error"
    case info = "info"
}

/// Push bildirim domain modeli.
struct PushNotification: Sendable, Identifiable {
    let id: UUID
    let category: NotificationCategory
    let title: String
    let body: String
    let deepLink: String?
    let badgeCount: Int
    let receivedAt: Date
}
```

## Business Rules

1. Device token backend'e kaydedilmeli. Ayni token birden fazla kez kaydedilirse (UPSERT) guncellenmeli.
2. Kullanici logout oldugunda device token silinmeli (is_active = false).
3. Her bildirim tipi icin kullanici bazli acma/kapama desteklenmeli.
4. Deep linking: `rafraf://chat/{session_id}`, `rafraf://approval/{approval_id}`, `rafraf://project/{project_id}` seklinde URL scheme kullanilmali.
5. Badge count backend tarafindan yonetilmeli, okunmamis bildirim sayisina gore guncellenmeli.
6. Bildirim izni isteme akisi: ilk acilista izin sorulmali, reddedilirse ayarlardan yonlendirilmeli.
7. In-app bildirim: uygulama on plandayken gelen bildirimler banner seklinde gosterilmeli.
8. APNs token her uygulama acilisinda yenilenmeli (Apple onerisi).

## Test Requirements

### Backend
- [ ] Unit test: NotificationService - bildirim gonderme lojigi
- [ ] Unit test: DeviceTokenRepository - token CRUD islemleri
- [ ] Integration test: POST /api/v1/notifications/device-token
- [ ] Integration test: DELETE /api/v1/notifications/device-token
- [ ] Integration test: GET /api/v1/notifications/settings
- [ ] Integration test: PATCH /api/v1/notifications/settings

### iOS
- [ ] Unit test: PushNotificationManager - token kayit akisi
- [ ] Unit test: NotificationRouter - deep link parsing
- [ ] Unit test: NotificationSettingsViewModel - ayar degisiklikleri
- [ ] Unit test: RegisterDeviceTokenUseCase
- [ ] Unit test: HandleNotificationUseCase

## Acceptance Criteria

- [ ] APNs token kaydi (backend'e gonder)
- [ ] Push bildirim alma ve gosterme
- [ ] Bildirim tipleri: task_complete, approval_needed, error, info
- [ ] Deep linking (bildirime tikla -> ilgili ekrana git)
- [ ] Badge count yonetimi
- [ ] Bildirim izni isteme akisi
- [ ] In-app bildirim banner'i
- [ ] Unit testler yazildi
- [ ] Coverage >= 70%
