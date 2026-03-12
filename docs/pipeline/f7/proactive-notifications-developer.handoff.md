# Developer Handoff: Proactive Notifications

**Issue**: #44
**Branch**: feature/f7/44-proactive-notifications
**Tarih**: 2026-03-13
**Sonraki Agent**: tester

## Yapilan Degisiklikler

| Dosya | Islem | Aciklama |
|-------|-------|----------|
| `apps/backend/app/models/proactive_notification.py` | CREATE | ProactiveNotification SQLAlchemy modeli |
| `apps/backend/app/models/__init__.py` | MODIFY | ProactiveNotification eklendi |
| `apps/backend/app/schemas/proactive_notification.py` | CREATE | Pydantic request/response semalari |
| `apps/backend/app/repositories/proactive_notification_repo.py` | CREATE | DB erisim katmani (CRUD, dedup, sayfalama) |
| `apps/backend/app/repositories/user_repository.py` | MODIFY | get_all_active metodu eklendi |
| `apps/backend/app/services/proactive_notification_service.py` | CREATE | Is mantigi, dedup, push dispatch |
| `apps/backend/app/api/routes/proactive_notifications.py` | CREATE | REST endpoint'leri (5 endpoint) |
| `apps/backend/app/api/routes/webhooks.py` | MODIFY | GitHub event -> proaktif bildirim tetikleme |
| `apps/backend/app/main.py` | MODIFY | Yeni router eklendi |
| `apps/ios/.../Domain/Models/ProactiveNotificationType.swift` | CREATE | Bildirim tipi enum |
| `apps/ios/.../Domain/Models/NotificationPriority.swift` | CREATE | Oncelik enum |
| `apps/ios/.../Domain/Models/ProactiveNotification.swift` | CREATE | Domain modeli |
| `apps/ios/.../Domain/Repositories/ProactiveNotificationRepositoryProtocol.swift` | CREATE | Repository protokolu |
| `apps/ios/.../Domain/UseCases/FetchNotificationsUseCase.swift` | CREATE | Bildirim listesi use case |
| `apps/ios/.../Domain/UseCases/MarkNotificationReadUseCase.swift` | CREATE | Okundu isaretleme use case |
| `apps/ios/.../Data/DTOs/ProactiveNotificationDTO.swift` | CREATE | API response DTO'lari |
| `apps/ios/.../Data/Mappers/ProactiveNotificationMapper.swift` | CREATE | DTO -> Domain mapper |
| `apps/ios/.../Data/Repositories/ProactiveNotificationRepositoryImpl.swift` | CREATE | REST API entegrasyonu |
| `apps/ios/.../Presentation/ViewModels/NotificationCenterViewModel.swift` | CREATE | Bildirim merkezi ViewModel |
| `apps/ios/.../Presentation/Views/NotificationCenterView.swift` | CREATE | Bildirim merkezi ekrani |
| `apps/ios/.../Presentation/Components/RFProactiveNotificationCard.swift` | CREATE | Bildirim kart bileseni |
| `shared/feature-specs/f7-44-proactive-notifications.md` | CREATE | Feature spec |
| `shared/api-contracts/rest/v1/proactive-notifications.json` | CREATE | REST API kontrati |
| `shared/api-contracts/ws/proactive-notification-messages.json` | CREATE | WebSocket kontrati |

## API Kontrat Uyumu

- Referans: `shared/api-contracts/rest/v1/proactive-notifications.json`
- 5 endpoint dogrulandi (GET list, PATCH read, POST read-all, DELETE, GET unread-count)
- Backend path'leri ve query param isimleri kontrat ile uyumlu
- iOS URLQueryItem key'leri kontrat ile uyumlu (snake_case)

## Dogrulama Sonuclari

| Arac | Durum | Detay |
|------|-------|-------|
| ruff check | SKIPPED | CI'da dogrulanacak |
| mypy | SKIPPED | CI'da dogrulanacak |
| pytest | SKIPPED | Test yoklugu — tester agent yazacak |
| xcodebuild build | SKIPPED | CI'da dogrulanacak |

## Notlar

- Backend proactive_notification tablosu icin Alembic migration tester/reviewer sonrasi olusturulacak
- WebSocket `proactive_notification` mesaj tipi webhook handler'dan broadcast ediliyor
- Dedup mekanizmasi `source_event` alanina dayali
- Urgent bildirimler mevcut APNs altyapisi ile push olarak da gonderiliyor
- iOS tarafinda Factory DI kaydini AppContainer'a ekleme sonraki adimda yapilacak
