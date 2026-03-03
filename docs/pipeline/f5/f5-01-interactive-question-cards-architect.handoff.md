# Architect Handoff: Interactive Question Cards (Approval + Countdown)

**Issue**: #30
**Faz**: F5
**Tarih**: 2026-03-03
**Sonraki Agent**: developer

## Ozet

iOS tarafinda kullanici onay gerektiren islemler icin interaktif kart componentleri. Backend'den WebSocket uzerinden gelen `question` mesajlarina karsilik, countdown timer ile onay/red akisi sunar. Multi-choice question destegi ve spring animasyonlu gosterim/kapanma saglar.

## Feature Spec

-> `shared/feature-specs/f5-30-f5-01-interactive-question-cards.md`

## API Contracts

-> `shared/api-contracts/ws/approval-messages.json` (mevcut — question ve approval_response mesaj tipleri)

API kontrati zaten mevcut. Yeni kontrat dosyasi olusturulmadi cunku backend approval system (issue #12) tarafindan tanimlanmis mesaj formatlari kullaniliyor.

## Katman Dagilimi

| Katman | Oncelik | Tahmini Dosya Sayisi |
|--------|---------|---------------------|
| ios | HIGH | 12 dosya |
| backend | N/A | 0 dosya (mevcut approval system kullaniliyor) |
| agent | N/A | 0 dosya |

## Dikkat Edilecekler

- **Mevcut WS kontrat**: `shared/api-contracts/ws/approval-messages.json` kontrati backend approval system (#12) ile birlikte olusturuldu. iOS tarafindaki DTO'lar bu kontrata BIREBIR uyumlu olmali.
- **WebSocketMessage entegrasyonu**: Mevcut `WebSocketMessageRouter` ve `WebSocketBaseMessage` yapisina uygun handler eklenmeli. Question mesaji icin `WebSocketContent` enum'ina yeni case eklenmeli.
- **RF* bilesen zorunlu**: Tum UI componentleri RF* prefix ile (`RFApprovalCard`, `RFCountdownTimer`, `RFApprovalOptionButton`).
- **Clean Architecture**: Data/Domain/Presentation katman izolasyonu saglanmali. Domain'den Data/Presentation import YASAK.
- **Chat entegrasyonu**: Approval card, chat akisinda inline gosterilecek. ChatView'a approval card rendering entegrasyonu gerekli.
- **Spring animation**: Kart gosterim/kapanma `spring` animation kullanmali.
- **Kategori bazli stil**: `destructive` ve `deploy` kategorileri icin kirmizi vurgu, diger kategoriler standart stil.
- **Bagimliliklarin durumu**: F4-04 (Chat view, #27) tamamlandi ve merged. F1-06 (Approval system backend, #12) spec mevcut.

## Dogrulama

- [x] Feature spec yazildi
- [x] API kontratlar mevcut (approval-messages.json)
- [x] Dosya sahipligi belirlendi
- [x] Doc referanslari kontrol edildi (docs/04, docs/07)
