# Architect Handoff: Proactive Notifications

**Issue**: #44
**Faz**: F7
**Tarih**: 2026-03-12
**Sonraki Agent**: developer

## Ozet

Proaktif bildirim sistemi: AI ve GitHub event'leri tarafindan tetiklenen bildirimler. Backend'de bildirim olusturma, saklama, onceliklendirme ve push. iOS'ta bildirim merkezi ekrani ile gecmis bildirimlere erisim, okundu/okunmadi yonetimi, gercek zamanli WebSocket push.

## Feature Spec

-> `shared/feature-specs/f7-44-proactive-notifications.md`

## API Contracts

-> `shared/api-contracts/rest/v1/proactive-notifications.json`
-> `shared/api-contracts/ws/proactive-notification-messages.json`

## Katman Dagilimi

| Katman | Oncelik | Tahmini Dosya Sayisi |
|--------|---------|---------------------|
| backend | HIGH | 7 dosya |
| ios | MEDIUM | 13 dosya |
| agent | N/A | 0 dosya |

## Dikkat Edilecekler

- Mevcut `NotificationService` ve `NotificationType` geniletilmeli, yeniden yazilmamali
- GitHub webhook handler (`webhooks.py`) proaktif bildirim olusturacak sekilde guncellenmeli
- Dedup mekanizmasi: `source_event` alani uzerinden ayni event icin tekrar bildirim engellenmeli
- Urgent bildirimler mevcut APNs altyapisi ile push notification olarak da gonderilmeli
- iOS'ta mevcut `NotificationCategory` enum'una yeni tipler eklenecek
- WebSocket uzerinden `proactive_notification` mesaj tipi ile gercek zamanli push
- Bildirim ayarlari mevcut NotificationSettings ile entegre (yeni tipler icin toggle ekle)

## Dogrulama

- [x] Feature spec yazildi
- [x] API kontratlar olusturuldu
- [x] Dosya sahipligi belirlendi
- [x] Doc referanslari kontrol edildi
