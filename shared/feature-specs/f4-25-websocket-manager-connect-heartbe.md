# Feature: WebSocket Manager (Connect, Heartbeat, Message Decode)

**Issue**: #25
**Faz**: F4
**Katmanlar**: ios
**Pipeline**: full
**Tarih**: 2026-03-03

## Ozet

iOS WebSocket baglanti yoneticisi. Backend'e URLSession native WebSocket ile baglanti kurma, otomatik yeniden baglanti (exponential backoff), heartbeat/ping-pong mekanizmasi, JSON mesaj encode/decode (Codable), connection state yonetimi (@Observable) ve background/foreground transition handling saglar. Bu feature, iOS uygulamasinin backend ile gercek zamanli iletisim kurabilmesi icin temel altyapidir.

## Degisecek Dosyalar

### iOS (`apps/ios/`)

| Dosya | Islem | Aciklama |
|-------|-------|----------|
| `RafRaf/Core/Networking/WebSocketClient.swift` | MODIFY | Mevcut basit WebSocket client'i genisletilecek: auto-reconnect, heartbeat, message routing |
| `RafRaf/Core/Networking/WebSocketMessage.swift` | CREATE | Codable WebSocket mesaj modelleri (BaseMessage, MessageMetadata, MessageAttachment) |
| `RafRaf/Core/Networking/WebSocketMessageRouter.swift` | CREATE | Mesaj tipi bazli routing ve handler dispatch |
| `RafRaf/Core/Networking/WebSocketConnectionManager.swift` | CREATE | @Observable connection state yonetimi, background/foreground handling |
| `RafRaf/Core/DI/AppContainer.swift` | MODIFY | WebSocketConnectionManager DI kaydini ekle |

## API Endpoints

### REST

Bu feature yeni REST endpoint gerektirmez.

### WebSocket Messages

| Direction | Type | Payload | Aciklama |
|-----------|------|---------|----------|
| server->client | `connection_ack` | `{user_id, session_id, server_time}` | Baglanti onay mesaji |
| client->server | `text` | `string` | Metin mesaji gonderme |
| server->client | `text` | `string` | AI metin cevabi |
| server->client | `error` | `{error_code, message, recoverable, details?, suggestion?}` | Hata mesaji |
| server->client | `progress` | `{task, step, total_steps, percentage, details?}` | Ilerleme bildirimi |
| bidirectional | `ping` | `{timestamp}` | Heartbeat ping |
| bidirectional | `pong` | `{timestamp}` | Heartbeat pong |

## Data Model

### PostgreSQL

Bu feature yeni DB tablosu gerektirmez.

### Swift Models

```swift
/// WebSocket baglanti durumlari
enum WebSocketConnectionState: Sendable {
    case disconnected
    case connecting
    case connected
    case reconnecting
}

/// Temel WebSocket mesaj yapisi
struct WebSocketBaseMessage: Codable, Sendable {
    let id: String
    let type: String
    let content: AnyCodableContent?
    let metadata: WebSocketMessageMetadata?
    let attachments: [WebSocketMessageAttachment]?
}

/// Mesaj metadata
struct WebSocketMessageMetadata: Codable, Sendable {
    let timestamp: String
    let sessionId: String?
    let projectId: String?
    let messageId: String?
    let direction: String
}

/// Mesaj ek dosyasi
struct WebSocketMessageAttachment: Codable, Sendable {
    let type: String
    let url: String
    let mimeType: String
    let sizeBytes: Int
}

/// Baglanti onay icerigi
struct ConnectionAckContent: Codable, Sendable {
    let userId: String
    let sessionId: String
    let serverTime: String
}

/// Hata mesaj icerigi
struct ErrorContent: Codable, Sendable {
    let errorCode: String
    let message: String
    let recoverable: Bool
    let details: String?
    let suggestion: String?
}

/// Ilerleme mesaj icerigi
struct ProgressContent: Codable, Sendable {
    let task: String
    let step: Int
    let totalSteps: Int
    let percentage: Int
    let details: String?
}

/// Ping/Pong icerigi
struct HeartbeatContent: Codable, Sendable {
    let timestamp: String
}
```

## Business Rules

1. **Auto-reconnect**: Baglanti koptiginda exponential backoff ile yeniden baglan (1s, 2s, 4s, 8s, max 60s)
2. **Heartbeat**: Her 30 saniyede ping gonder, 10 saniye icinde pong gelmezse baglanti kopmus say
3. **Connection state**: `@Observable` ile UI'a reaktif state bildirimi
4. **Background handling**: Uygulama background'a gectiginde baglanti kapat, foreground'a donunce yeniden baglan
5. **Message routing**: Gelen mesajlari `type` field'ina gore ilgili handler'a yonlendir
6. **Thread safety**: Actor-based isolation ile thread-safe WebSocket islemleri
7. **JSON encode/decode**: Tum mesajlar `shared/api-contracts/ws/websocket-messages.json` kontratina uygun Codable struct'lar ile
8. **Logging**: Tum baglanti olaylari ve hatalar `os.Logger` ile loglanir

## Test Requirements

### iOS
- [ ] Unit test: WebSocketMessage encode/decode (tum mesaj tipleri)
- [ ] Unit test: WebSocketMessageRouter — dogru handler'a yonlendirme
- [ ] Unit test: WebSocketConnectionManager — state gecisleri (disconnected -> connecting -> connected -> reconnecting)
- [ ] Unit test: Auto-reconnect exponential backoff hesaplamasi
- [ ] Unit test: Heartbeat timeout tespiti
- [ ] Unit test: Background/foreground gecisleri

## Acceptance Criteria

- [ ] URLSession native WebSocket baglanti kurulur
- [ ] Auto-reconnect exponential backoff ile calisir (1s, 2s, 4s, 8s, max 60s)
- [ ] Heartbeat/ping-pong mekanizmasi 30s aralikla calisir
- [ ] JSON message encode/decode tum mesaj tipleri icin calisir (Codable)
- [ ] Connection state @Observable ile yonetilir
- [ ] Background/foreground transition handling dogru calisir
- [ ] Message type routing sistemi mesajlari dogru handler'a yonlendirir
- [ ] Unit testler yazildi (mock WebSocket)
- [ ] Coverage >= 70%
