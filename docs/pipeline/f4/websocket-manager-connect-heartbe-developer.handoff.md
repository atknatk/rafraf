# Developer Handoff: WebSocket Manager (Connect, Heartbeat, Message Decode)

**Issue**: #25
**Branch**: feature/f4/25-websocket-manager-connect-heartbe
**Tarih**: 2026-03-03
**Sonraki Agent**: tester

## Yapilan Degisiklikler

| Dosya | Islem | Aciklama |
|-------|-------|----------|
| `apps/ios/RafRaf/Core/Networking/WebSocketClient.swift` | MODIFY | Auto-reconnect, heartbeat, mesaj dinleme loop eklendi |
| `apps/ios/RafRaf/Core/Networking/WebSocketMessage.swift` | CREATE | Codable mesaj modelleri (BaseMessage, Content, Metadata, Attachment, Factory) |
| `apps/ios/RafRaf/Core/Networking/WebSocketMessageRouter.swift` | CREATE | Type bazli mesaj yonlendirme, handler kaydi, JSON encode/decode |
| `apps/ios/RafRaf/Core/Networking/WebSocketConnectionManager.swift` | CREATE | @Observable state yonetimi, background/foreground handling |
| `apps/ios/RafRaf/Core/DI/AppContainer.swift` | MODIFY | WebSocketMessageRouter, WebSocketConnectionManager DI kayitlari |

## Dogrulama Sonuclari

| Arac | Durum | Detay |
|------|-------|-------|
| xcodebuild build | PASS | 0 error, 0 warning |

## API Kontrat Uyumu

- Referans kontrat: `shared/api-contracts/ws/websocket-messages.json`
- Dogrulanan mesaj tipleri: connection_ack, text, error, progress, ping, pong
- Tum Codable struct'lar kontrat'a uygun field isim ve tipleri ile olusturuldu
- snake_case <-> camelCase donusumu JSONDecoder/JSONEncoder ile saglanir

## Notlar

- `WebSocketClient` actor olarak implement edildi (thread safety)
- `WebSocketConnectionManager` @MainActor @Observable class olarak implement edildi (UI binding icin)
- Auto-reconnect: exponential backoff (1s, 2s, 4s, 8s, max 60s)
- Heartbeat: 30s aralik, 10s pong timeout
- Background'a geciste disconnect, foreground'a donuste reconnect
- `WebSocketContent` enum ile tip-guvenli content decode (text, connectionAck, error, progress, heartbeat)
- `ObserverStorage` helper class ile deinit'ten NotificationCenter observer temizligi
- Tester icin: Mock WebSocketClient protocol cikarilabilir, state gecisleri ve mesaj routing test edilebilir
