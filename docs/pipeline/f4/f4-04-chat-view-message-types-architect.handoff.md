# Architect Handoff: Chat View + Message Types

**Issue**: #27
**Faz**: F4
**Tarih**: 2026-03-03
**Sonraki Agent**: developer

## Ozet

Ana sohbet ekrani implementasyonu. Text, code, image, file, system mesaj tipleri, AI streaming response, typing indicator, mesaj gecmisi pagination, Markdown rendering ve mesaj kopyalama ozellikleri. Sadece iOS katmanini etkiler - backend WS altyapisi mevcut.

## Feature Spec

-> `shared/feature-specs/f4-27-f4-04-chat-view-message-types.md`

## API Contracts

-> `shared/api-contracts/ws/chat-messages.json`

Mevcut WebSocket altyapisi (`shared/api-contracts/ws/websocket-messages.json`) uzerine chat'e ozel mesaj tipleri eklendi:
- `chat.send` (client -> server)
- `chat.message` (server -> client)
- `chat.stream` / `chat.stream_end` (server -> client, streaming)
- `chat.typing` (server -> client)
- `chat.history` / `chat.history_response` (bidirectional, pagination)

## Katman Dagilimi

| Katman | Oncelik | Tahmini Dosya Sayisi |
|--------|---------|---------------------|
| ios | HIGH | 16 dosya (6 modify + 10 create) |
| backend | N/A | Degisiklik yok - mevcut WS altyapisi yeterli |
| agent | N/A | Degisiklik yok |

## Dikkat Edilecekler

- Mevcut `ChatMessage`, `ChatMessageDTO`, `ChatMessageMapper`, `ChatRepositoryProtocol`, `ChatViewModel`, `ChatView` dosyalari MEVCUT - bunlar genisletilecek (MODIFY), sifirdan yazilmayacak
- WebSocket baglantisi `RFWebSocketService` (Core/Network) uzerinden yapilir - F4-02'de implemente edildi
- RF* Design System bilesenleri mevcut: RFButton, RFCard, RFTextField, RFText, RFLoadingView, RFEmptyStateView, RFColors, RFSpacing, RFTypography
- Yeni RF* bilesenleri: RFMessageBubble, RFChatInput, RFTypingIndicator, RFCodeBlock, RFImageMessageView
- Clean Architecture katman izolasyonu korunmali: Domain'den Data/Presentation import YASAK
- Tum stringler `String(localized:)` ile
- Her view'da `#Preview` blogu olmali
- `@Observable` + `@MainActor` ViewModel pattern

## Bagimlilikllar

- F4-02 (WebSocket manager) - MEVCUT, merge edilmis
- F4-01 (iOS scaffold + tab nav + design system) - MEVCUT, merge edilmis

## Dogrulama

- [x] Feature spec yazildi
- [x] API kontratlar olusturuldu (WS chat mesajlari)
- [x] Dosya sahipligi belirlendi
- [x] Doc referanslari kontrol edildi (docs/04, docs/02)
