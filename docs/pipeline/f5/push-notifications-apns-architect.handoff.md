# Architect Handoff: Push Notifications (APNs)

**Issue**: #36
**Faz**: F5
**Tarih**: 2026-03-03
**Sonraki Agent**: developer

## Ozet

Push bildirim sistemi iOS cihazlara APNs uzerinden bildirim gonderir. Backend'de device token yonetimi, bildirim ayarlari ve bildirim gonderme servisi olusturulur. iOS'ta UNUserNotificationCenter ile bildirim alma, deep linking ile ilgili ekrana yonlendirme ve in-app bildirim banner'i saglanir.

## Feature Spec

-> `shared/feature-specs/f5-36-push-notifications-apns.md`

## API Contracts

-> `shared/api-contracts/rest/v1/notifications.json`

## Katman Dagilimi

| Katman | Oncelik | Tahmini Dosya Sayisi |
|--------|---------|---------------------|
| backend | HIGH | 6 dosya |
| ios | HIGH | 17 dosya |
| agent | N/A | 0 dosya |

## Dikkat Edilecekler

- Backend: APNs ile dogrudan iletisim icin `aioapns` veya benzeri async library kullanilabilir. Ancak bu feature'da backend APNs token kaydi ve bildirim gonderme altyapisini kurar. Gercek APNs push icin Apple Developer sertifikasi gerekir.
- iOS: UNUserNotificationCenter delegate'i AppDelegate'te tanimlanmali (SwiftUI @main struct yerine UIApplicationDelegateAdaptor kullanilacak).
- Deep linking URL scheme: `rafraf://` prefix'i ile. Parse islemi NotificationRouter'da yapilir.
- Badge count: backend'den gelen badge sayisi ile guncellenir. Uygulama acildiginda sifirlanir.
- Bildirim izni: requestAuthorization ile .alert, .badge, .sound izinleri istenir.
- Mevcut Settings feature'daki NotificationType enum ve AppSettings.pushNotificationsEnabled ile entegrasyon yapilmali.

## Dogrulama

- [x] Feature spec yazildi
- [x] API kontratlar olusturuldu
- [x] Dosya sahipligi belirlendi
- [x] Doc referanslari kontrol edildi
