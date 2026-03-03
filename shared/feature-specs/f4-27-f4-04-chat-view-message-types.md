# Feature: Chat View + Message Types

**Issue**: #27
**Faz**: F4
**Katmanlar**: ios
**Pipeline**: full
**Tarih**: 2026-03-03

## Ozet

Ana sohbet ekrani. Kullanici ile AI asistan arasindaki metin tabanli iletisimi saglar. Mesaj tipleri (text, code, image, file, system), AI streaming response gosterimi, typing indicator, mesaj gecmisi (scroll + pagination), Markdown rendering (kod bloklari dahil), mesaj kopyalama ve RF* componentler ile tam donanimli chat deneyimi sunar.

## Degisecek Dosyalar

### iOS (`apps/ios/`)

| Dosya | Islem | Aciklama |
|-------|-------|----------|
| `RafRaf/Features/Chat/Domain/Models/ChatMessage.swift` | MODIFY | Mesaj tipleri genisletildi (code, image, file, attachment destegi) |
| `RafRaf/Features/Chat/Domain/Models/ChatAttachment.swift` | CREATE | Dosya/gorsel ek modeli |
| `RafRaf/Features/Chat/Domain/Repositories/ChatRepositoryProtocol.swift` | MODIFY | Mesaj gecmisi pagination, streaming destegi |
| `RafRaf/Features/Chat/Domain/UseCases/SendMessageUseCase.swift` | CREATE | Mesaj gonderme is mantigi |
| `RafRaf/Features/Chat/Domain/UseCases/LoadChatHistoryUseCase.swift` | CREATE | Mesaj gecmisi yukleme (pagination) |
| `RafRaf/Features/Chat/Data/DTOs/ChatMessageDTO.swift` | MODIFY | Genisletilmis DTO (attachment, metadata) |
| `RafRaf/Features/Chat/Data/DTOs/ChatAttachmentDTO.swift` | CREATE | Attachment DTO |
| `RafRaf/Features/Chat/Data/Mappers/ChatMessageMapper.swift` | MODIFY | Yeni alanlar icin donusum |
| `RafRaf/Features/Chat/Data/Repositories/ChatRepositoryImpl.swift` | CREATE | WS + REST repository impl |
| `RafRaf/Features/Chat/Presentation/ViewModels/ChatViewModel.swift` | MODIFY | Tam feature ViewModel (mesaj listesi, streaming, pagination, typing) |
| `RafRaf/Features/Chat/Presentation/Views/ChatView.swift` | MODIFY | Tam chat ekrani (mesaj listesi + input bar) |
| `RafRaf/Features/Chat/Presentation/Components/RFMessageBubble.swift` | CREATE | Mesaj baloncugu (text, code, image, file, system) |
| `RafRaf/Features/Chat/Presentation/Components/RFChatInput.swift` | CREATE | Chat girdi cubugu (metin + gonder + ek) |
| `RafRaf/Features/Chat/Presentation/Components/RFTypingIndicator.swift` | CREATE | AI yazma gostergesi |
| `RafRaf/Features/Chat/Presentation/Components/RFCodeBlock.swift` | CREATE | Kod blogu goruntuleme + kopyalama |
| `RafRaf/Features/Chat/Presentation/Components/RFImageMessageView.swift` | CREATE | Gorsel mesaj goruntuleme |

## API Endpoints

### REST

Bu feature yeni REST endpoint EKLEMEZ. Mevcut backend WS altyapisi kullanilir.

### WebSocket Messages

Mevcut `shared/api-contracts/ws/websocket-messages.json` kontratindaki mesajlar kullanilir. Ek olarak chat'e ozel mesaj tipleri eklenir:

| Direction | Type | Payload | Aciklama |
|-----------|------|---------|----------|
| client_to_server | `chat.send` | `ChatSendPayload` | Kullanici mesaj gonderir |
| server_to_client | `chat.message` | `ChatMessagePayload` | AI tam mesaj cevabi |
| server_to_client | `chat.stream` | `ChatStreamPayload` | AI streaming parca |
| server_to_client | `chat.stream_end` | `ChatStreamEndPayload` | Streaming bitti |
| server_to_client | `chat.typing` | `ChatTypingPayload` | AI yaziyor gostergesi |
| client_to_server | `chat.history` | `ChatHistoryRequest` | Mesaj gecmisi iste |
| server_to_client | `chat.history_response` | `ChatHistoryResponse` | Mesaj gecmisi cevabi |

## Data Model

### Swift Models

```swift
// Domain Model - ChatMessage (genisletilmis)
struct ChatMessage: Identifiable, Sendable, Equatable {
    let id: String
    let content: String
    let sender: MessageSender
    let timestamp: Date
    let type: MessageType
    let attachments: [ChatAttachment]
    let isStreaming: Bool
}

enum MessageSender: String, Sendable, Equatable {
    case user
    case assistant
    case system
}

enum MessageType: String, Sendable, Equatable, CaseIterable {
    case text
    case code
    case image
    case file
    case system
}

struct ChatAttachment: Identifiable, Sendable, Equatable {
    let id: String
    let type: AttachmentType
    let url: String
    let mimeType: String
    let sizeBytes: Int
}

enum AttachmentType: String, Sendable, Equatable {
    case image
    case file
    case audio
}
```

## Business Rules

1. Mesaj bos gonderilEMEZ (minimum 1 karakter)
2. Maksimum mesaj uzunlugu 4096 karakter
3. AI cevabi streaming olarak gelir, her parca anlik gosterilir
4. Typing indicator AI yanit uretmeye basladiginda gosterilir, cevap geldiginde kaybolur
5. Mesaj gecmisi ilk 20 mesaj yuklenir, scroll ile pagination (cursor-based)
6. Markdown rendering: bold, italic, code blocks (syntax highlighted), linkler desteklenir
7. Kod bloklari kopyalanabilir (tek tikla kopyala)
8. Mesaj baloncugu: kullanici mesajlari sagda (userBubble renk), AI mesajlari solda (aiBubble renk)
9. System mesajlari ortada, farkli stilde (acik gri, kucuk font)
10. Image mesajlari inline goruntulenir, tiklaninca tam ekran acilir

## Test Requirements

### iOS
- [ ] Unit test: ChatViewModel mesaj gonderme (bos mesaj engelleme)
- [ ] Unit test: ChatViewModel streaming state yonetimi
- [ ] Unit test: ChatViewModel pagination (cursor guncelleme)
- [ ] Unit test: SendMessageUseCase basari ve hata senaryolari
- [ ] Unit test: LoadChatHistoryUseCase basari ve hata senaryolari
- [ ] Unit test: ChatMessageMapper DTO -> Domain donusum
- [ ] Unit test: ChatAttachment model eslesmesi
- [ ] Unit test: MessageType tum case'ler icin render dogrulama

## Acceptance Criteria

- [ ] Chat view (mesaj listesi + input bar)
- [ ] Mesaj tipleri: text, code, image, file, system
- [ ] AI streaming response gosterimi
- [ ] Typing indicator
- [ ] Mesaj gecmisi (scroll + pagination)
- [ ] Markdown rendering (kod bloklari dahil)
- [ ] Mesaj kopyalama
- [ ] RF* componentler ile (RFMessageBubble, RFChatInput, vb.)
- [ ] #Preview
- [ ] Unit testler yazildi
- [ ] Coverage >= 70%
