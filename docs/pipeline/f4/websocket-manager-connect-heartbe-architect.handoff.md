# Architect Handoff: WebSocket Manager (Connect, Heartbeat, Message Decode)

**Issue**: #25
**Faz**: F4
**Tarih**: 2026-03-03
**Sonraki Agent**: developer

## Ozet

iOS WebSocket baglanti yoneticisi. Mevcut basit `WebSocketClient` actor'unu genisletip auto-reconnect (exponential backoff), heartbeat/ping-pong, JSON mesaj encode/decode (Codable), @Observable connection state yonetimi ve background/foreground transition handling eklenecek. Sadece iOS katmanini etkiler.

## Feature Spec

-> `shared/feature-specs/f4-25-websocket-manager-connect-heartbe.md`

## API Contracts

-> `shared/api-contracts/ws/websocket-messages.json` (mevcut, yeni kontrat gerekmez)

## Katman Dagilimi

| Katman | Oncelik | Tahmini Dosya Sayisi |
|--------|---------|---------------------|
| ios | HIGH | 5 dosya (1 modify, 4 create/modify) |
| backend | N/A | 0 dosya |
| agent | N/A | 0 dosya |

## Dikkat Edilecekler

- Mevcut `WebSocketClient` actor yapisi korunmali, genisletilmeli
- `shared/api-contracts/ws/websocket-messages.json` kontratina tam uyum saglanmali
- `URLSession` native WebSocket kullanilmali (3rd party YASAK)
- `@Observable` connection state yonetimi icin ayri `WebSocketConnectionManager` class'i olusturulmali (actor'dan farkli, UI binding icin)
- Factory DI ile tum yeni servisler `AppContainer`'a kaydedilmeli
- iOS 17+ minimum, Swift 6 concurrency uyumu
- `os.Logger` ile structured logging
- Background/foreground gecisleri `NotificationCenter` ile dinlenmeli

## Dogrulama

- [x] Feature spec yazildi
- [x] API kontratlar mevcut (websocket-messages.json)
- [x] Dosya sahipligi belirlendi
- [x] Doc referanslari kontrol edildi (docs/02, docs/04)
