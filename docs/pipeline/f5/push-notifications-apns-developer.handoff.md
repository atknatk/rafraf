# Developer Handoff: Push Notifications (APNs)

**Issue**: #36
**Branch**: feature/f5/36-push-notifications-apns
**Tarih**: 2026-03-03
**Sonraki Agent**: tester

## Yapilan Degisiklikler

| Dosya | Islem | Aciklama |
|-------|-------|----------|
| `apps/backend/app/models/device_token.py` | CREATE | DeviceToken + NotificationSettings SQLAlchemy modelleri |
| `apps/backend/app/schemas/notifications.py` | CREATE | Pydantic request/response schemalar |
| `apps/backend/app/repositories/device_token_repo.py` | CREATE | Device token ve bildirim ayarlari DB repository |
| `apps/backend/app/services/notification_service.py` | CREATE | Push bildirim servisi (token yonetimi, dispatch) |
| `apps/backend/app/api/routes/notifications.py` | CREATE | REST endpoint'leri (4 endpoint) |
| `apps/backend/app/main.py` | MODIFY | Notification router kaydı |
| `apps/ios/RafRaf/Core/Notifications/PushNotificationManager.swift` | CREATE | APNs token yonetimi, izin isteme, bildirim isleme |
| `apps/ios/RafRaf/Core/Notifications/NotificationRouter.swift` | CREATE | Deep link parser (rafraf:// URL scheme) |
| `apps/ios/RafRaf/App/AppDelegate.swift` | CREATE | UIApplicationDelegate + UNUserNotificationCenterDelegate |
| `apps/ios/RafRaf/App/RafRafApp.swift` | MODIFY | UIApplicationDelegateAdaptor eklendi |
| `apps/ios/RafRaf/Features/Notifications/Data/DTOs/DeviceTokenDTO.swift` | CREATE | Token kayit/silme DTO'lari |
| `apps/ios/RafRaf/Features/Notifications/Data/DTOs/NotificationPayloadDTO.swift` | CREATE | Bildirim ayarlari DTO'lari |
| `apps/ios/RafRaf/Features/Notifications/Data/Mappers/NotificationMapper.swift` | CREATE | DTO <-> Domain model mapper |
| `apps/ios/RafRaf/Features/Notifications/Data/Repositories/NotificationRepositoryImpl.swift` | CREATE | REST API uzerinden bildirim islemleri |
| `apps/ios/RafRaf/Features/Notifications/Domain/Models/NotificationCategory.swift` | CREATE | Bildirim kategorileri enum |
| `apps/ios/RafRaf/Features/Notifications/Domain/Models/PushNotification.swift` | CREATE | Bildirim domain modeli |
| `apps/ios/RafRaf/Features/Notifications/Domain/Repositories/NotificationRepositoryProtocol.swift` | CREATE | Repository protocol + yardimci tipler |
| `apps/ios/RafRaf/Features/Notifications/Domain/UseCases/RegisterDeviceTokenUseCase.swift` | CREATE | Token kayit use case |
| `apps/ios/RafRaf/Features/Notifications/Domain/UseCases/HandleNotificationUseCase.swift` | CREATE | Bildirim isleme use case |
| `apps/ios/RafRaf/Features/Notifications/Presentation/ViewModels/NotificationSettingsViewModel.swift` | CREATE | Bildirim ayarlari ViewModel |
| `apps/ios/RafRaf/Features/Notifications/Presentation/Views/NotificationSettingsView.swift` | CREATE | Bildirim ayarlari ekrani |
| `apps/ios/RafRaf/Features/Notifications/Presentation/Components/RFNotificationBanner.swift` | CREATE | In-app bildirim banner bileseni |
| `apps/ios/RafRaf/Core/DI/AppContainer.swift` | MODIFY | Notification DI kayitlari |

## API Kontrat Uyumu

- Referans: `shared/api-contracts/rest/v1/notifications.json`
- 4 endpoint dogrulandi (POST token, DELETE token, GET settings, PATCH settings)
- Tum path, method ve field isimleri kontrat ile uyumlu

## Dogrulama Sonuclari

| Arac | Durum | Detay |
|------|-------|-------|
| ruff check | N/A | CI'da dogrulanacak |
| mypy | N/A | CI'da dogrulanacak |
| pytest | N/A | Tester agent tarafindan calistirilacak |
| swiftlint | N/A | CI'da dogrulanacak |
| xcodebuild build | N/A | CI'da dogrulanacak |
| xcodebuild test | N/A | Tester agent tarafindan calistirilacak |

## Notlar

- Backend: APNs gercek push gonderimi icin Apple Developer sertifikasi gerekir. notification_service.py'de dispatch mekanizmasi hazir ama gercek APNs baglantisi kurulmadi (aioapns veya benzeri kutuphanle entegre edilecek).
- iOS: UIApplicationDelegateAdaptor ile AppDelegate eklendi. UNUserNotificationCenterDelegate on-plan ve arka-plan bildirim handling saglar.
- Deep linking: `rafraf://chat/{id}`, `rafraf://approval/{id}`, `rafraf://project/{id}`, `rafraf://settings` desteklenir.
- Badge count: Backend'den gelen badge sayisi ile guncellenir, uygulama acildiginda sifirlanir.
- Mevcut Settings feature'daki bildirim toggle'lari ile bu feature'in backend ayarlari entegre calisir.
