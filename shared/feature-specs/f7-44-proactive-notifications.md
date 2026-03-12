# Feature: Proactive Notifications

**Issue**: #44
**Faz**: F7
**Katmanlar**: backend, ios
**Pipeline**: full
**Tarih**: 2026-03-12

## Ozet

Proaktif bildirim sistemi, AI'in kullaniciya kendilinden bildirim gondermesini saglar. Gorev tamamlandi, sorun tespit edildi, oneri ve hatirlatma gibi bildirim tipleri desteklenir. GitHub event'lerine (PR merge, CI fail vb.) tepki vererek otomatik bildirim uretir. Bildirimler onceliklendirilerek (urgent, normal, low) iOS'ta gosterilir ve gecmis bildirimlere erisilebilir.

## Degisecek Dosyalar

### Backend (`apps/backend/`)
| Dosya | Islem | Aciklama |
|-------|-------|----------|
| `app/models/proactive_notification.py` | CREATE | Proaktif bildirim SQLAlchemy modeli |
| `app/schemas/proactive_notification.py` | CREATE | Proaktif bildirim Pydantic semalari |
| `app/repositories/proactive_notification_repo.py` | CREATE | Proaktif bildirim DB erisim katmani |
| `app/services/proactive_notification_service.py` | CREATE | Proaktif bildirim is mantigi + AI onceliklendirme |
| `app/api/routes/proactive_notifications.py` | CREATE | REST endpoint'leri (liste, okundu isaretleme, silme) |
| `app/api/routes/webhooks.py` | MODIFY | GitHub event'lerinden proaktif bildirim tetikleme |
| `app/schemas/notifications.py` | MODIFY | Yeni bildirim tipleri ekleme |

### iOS (`apps/ios/`)
| Dosya | Islem | Aciklama |
|-------|-------|----------|
| `RafRaf/Features/Notifications/Data/DTOs/ProactiveNotificationDTO.swift` | CREATE | Proaktif bildirim DTO |
| `RafRaf/Features/Notifications/Data/Repositories/ProactiveNotificationRepositoryImpl.swift` | CREATE | Repository implementasyonu |
| `RafRaf/Features/Notifications/Data/Mappers/ProactiveNotificationMapper.swift` | CREATE | DTO -> Domain mapper |
| `RafRaf/Features/Notifications/Domain/Models/ProactiveNotification.swift` | CREATE | Domain modeli |
| `RafRaf/Features/Notifications/Domain/Models/NotificationPriority.swift` | CREATE | Oncelik enum'u |
| `RafRaf/Features/Notifications/Domain/Models/ProactiveNotificationType.swift` | CREATE | Proaktif bildirim tipi enum |
| `RafRaf/Features/Notifications/Domain/Repositories/ProactiveNotificationRepositoryProtocol.swift` | CREATE | Repository protokolu |
| `RafRaf/Features/Notifications/Domain/UseCases/FetchNotificationsUseCase.swift` | CREATE | Bildirim listesi getirme |
| `RafRaf/Features/Notifications/Domain/UseCases/MarkNotificationReadUseCase.swift` | CREATE | Okundu isaretleme |
| `RafRaf/Features/Notifications/Presentation/ViewModels/NotificationCenterViewModel.swift` | CREATE | Bildirim merkezi ViewModel |
| `RafRaf/Features/Notifications/Presentation/Views/NotificationCenterView.swift` | CREATE | Bildirim merkezi ekrani |
| `RafRaf/Features/Notifications/Presentation/Components/RFProactiveNotificationCard.swift` | CREATE | Bildirim kart bileseni |
| `RafRaf/Features/Notifications/Domain/Models/NotificationCategory.swift` | MODIFY | Yeni kategoriler ekleme |

## API Endpoints

### REST
| Method | Path | Request | Response | Aciklama |
|--------|------|---------|----------|----------|
| GET | `/api/v1/proactive-notifications` | Query: page, page_size, priority, is_read, type | `ProactiveNotificationListResponse` | Bildirim listesi (sayfalanmis) |
| PATCH | `/api/v1/proactive-notifications/{notification_id}/read` | - | `ProactiveNotificationResponse` | Bildirimi okundu isaretle |
| POST | `/api/v1/proactive-notifications/read-all` | - | `{marked_count: int}` | Tum bildirimleri okundu isaretle |
| DELETE | `/api/v1/proactive-notifications/{notification_id}` | - | 204 No Content | Bildirim silme |
| GET | `/api/v1/proactive-notifications/unread-count` | - | `{count: int}` | Okunmamis bildirim sayisi |

### WebSocket Messages
| Direction | Type | Payload | Aciklama |
|-----------|------|---------|----------|
| server->client | `proactive_notification` | `ProactiveNotificationPayload` | Yeni proaktif bildirim |

## Data Model

### PostgreSQL
```sql
CREATE TABLE proactive_notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    type VARCHAR(50) NOT NULL,
    priority VARCHAR(20) NOT NULL DEFAULT 'normal',
    title VARCHAR(500) NOT NULL,
    body TEXT NOT NULL,
    source VARCHAR(100) NOT NULL,
    source_event VARCHAR(200),
    deep_link VARCHAR(1000),
    metadata JSONB DEFAULT '{}',
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    read_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_proactive_notifications_user_id ON proactive_notifications(user_id);
CREATE INDEX idx_proactive_notifications_user_unread ON proactive_notifications(user_id, is_read) WHERE is_read = FALSE;
CREATE INDEX idx_proactive_notifications_created_at ON proactive_notifications(created_at DESC);
```

### Pydantic Models
```python
class ProactiveNotificationType(StrEnum):
    task_complete = "task_complete"
    issue_detected = "issue_detected"
    suggestion = "suggestion"
    reminder = "reminder"
    ci_failure = "ci_failure"
    pr_merged = "pr_merged"
    security_alert = "security_alert"


class NotificationPriority(StrEnum):
    urgent = "urgent"
    normal = "normal"
    low = "low"


class ProactiveNotificationResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    type: ProactiveNotificationType
    priority: NotificationPriority
    title: str
    body: str
    source: str
    source_event: str | None
    deep_link: str | None
    metadata: dict[str, str]
    is_read: bool
    read_at: datetime | None
    created_at: datetime
```

### Swift Models
```swift
struct ProactiveNotification: Sendable, Identifiable, Equatable {
    let id: UUID
    let type: ProactiveNotificationType
    let priority: NotificationPriority
    let title: String
    let body: String
    let source: String
    let sourceEvent: String?
    let deepLink: String?
    let metadata: [String: String]
    let isRead: Bool
    let readAt: Date?
    let createdAt: Date
}

enum ProactiveNotificationType: String, Sendable, CaseIterable {
    case taskComplete = "task_complete"
    case issueDetected = "issue_detected"
    case suggestion = "suggestion"
    case reminder = "reminder"
    case ciFailure = "ci_failure"
    case prMerged = "pr_merged"
    case securityAlert = "security_alert"
}

enum NotificationPriority: String, Sendable, CaseIterable, Comparable {
    case urgent = "urgent"
    case normal = "normal"
    case low = "low"
}
```

## Business Rules

1. GitHub webhook event'leri (PR merge, CI fail, issue acilma) proaktif bildirim olarak kaydedilir
2. Bildirim onceligi kaynak event tipine gore belirlenir: CI failure -> urgent, PR merged -> normal, suggestion -> low
3. Ayni source_event icin tekrar bildirim uretilmez (dedup mekanizmasi)
4. Okunmamis bildirim sayisi WebSocket uzerinden iOS'a push edilir
5. 30 gunluk eski bildirimler otomatik temizlenir
6. Kullanici bildirim tipi bazli ayarlarla istedigi kategorileri kapatabilir (mevcut NotificationSettings ile entegre)
7. Urgent bildirimler push notification olarak da gonderilir (mevcut APNs altyapisi kullanilir)

## Test Requirements

### Backend
- [ ] Unit test: ProactiveNotificationService.create_notification
- [ ] Unit test: ProactiveNotificationService.get_notifications (filtreleme, sayfalama)
- [ ] Unit test: ProactiveNotificationService.mark_read / mark_all_read
- [ ] Unit test: Dedup mekanizmasi (ayni source_event icin tekrar bildirim engellenmeli)
- [ ] Integration test: Webhook -> proaktif bildirim akisi
- [ ] Integration test: REST endpoint'leri (CRUD)
- [ ] Integration test: WebSocket proactive_notification mesaji

### iOS
- [ ] Unit test: ProactiveNotificationMapper
- [ ] Unit test: FetchNotificationsUseCase
- [ ] Unit test: MarkNotificationReadUseCase
- [ ] Unit test: NotificationCenterViewModel (state yonetimi)
- [ ] UI test: NotificationCenterView bildirim listesi gorunumu

## Acceptance Criteria

- [ ] Proaktif bildirim tetikleme mekanizmasi (GitHub webhook -> bildirim)
- [ ] Bildirim tipleri: task_complete, issue_detected, suggestion, reminder, ci_failure, pr_merged, security_alert
- [ ] GitHub event'lerine tepki (PR merge, CI fail)
- [ ] Bildirim onceliklendirme (urgent, normal, low)
- [ ] iOS'ta bildirim merkezi ekrani
- [ ] Bildirim gecmisi (sayfalanmis liste)
- [ ] Okundu/okunmadi durumu
- [ ] Okunmamis bildirim sayaci (badge)
- [ ] WebSocket uzerinden gercek zamanli bildirim push
