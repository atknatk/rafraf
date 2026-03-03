import Foundation
import os

/// Sohbet ViewModel.
/// Chat ekraninin durumunu ve islemlerini yonetir.
/// Mesaj gonderme, streaming, typing indicator, pagination destegi.
@Observable
@MainActor
final class ChatViewModel {
    // MARK: - State

    var messages: [ChatMessage] = []
    var messageText: String = ""
    var isLoading: Bool = false
    var isSending: Bool = false
    var isTyping: Bool = false
    var errorMessage: String?
    var hasMoreMessages: Bool = false

    // MARK: - Private

    private let sendMessageUseCase: SendMessageUseCase
    private let loadHistoryUseCase: LoadChatHistoryUseCase
    private let sessionId: String
    private var nextCursor: String?
    private var isLoadingMore: Bool = false
    private let logger = AppLogger.logger(for: "Chat")

    // MARK: - Init

    init(
        sendMessageUseCase: SendMessageUseCase,
        loadHistoryUseCase: LoadChatHistoryUseCase,
        sessionId: String = UUID().uuidString
    ) {
        self.sendMessageUseCase = sendMessageUseCase
        self.loadHistoryUseCase = loadHistoryUseCase
        self.sessionId = sessionId
        logger.info("ChatViewModel baslatildi - session: \(sessionId)")
    }

    // MARK: - Actions

    /// Mesaj gonderir.
    func sendMessage() async {
        let text = messageText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }

        messageText = ""
        isSending = true
        errorMessage = nil

        do {
            let sentMessage = try await sendMessageUseCase.execute(
                text: text,
                sessionId: sessionId
            )
            messages.append(sentMessage)
            logger.info("Mesaj gonderildi: \(sentMessage.id)")
        } catch {
            errorMessage = String(localized: "chat.error.sendFailed")
            logger.error("Mesaj gonderme hatasi: \(error.localizedDescription)")
            // Mesaj metnini geri yukle kullanici tekrar deneyebilsin
            messageText = text
        }

        isSending = false
    }

    /// Mesaj gecmisini yukler (ilk sayfa).
    func loadHistory() async {
        guard !isLoading else { return }

        isLoading = true
        errorMessage = nil

        do {
            let result = try await loadHistoryUseCase.execute(
                sessionId: sessionId,
                cursor: nil
            )
            messages = result.messages
            hasMoreMessages = result.hasMore
            nextCursor = result.nextCursor
            logger.info("Mesaj gecmisi yuklendi: \(result.messages.count) mesaj")
        } catch {
            errorMessage = String(localized: "chat.error.loadFailed")
            logger.error("Gecmis yukleme hatasi: \(error.localizedDescription)")
        }

        isLoading = false
    }

    /// Daha fazla mesaj yukler (pagination).
    func loadMoreMessages() async {
        guard hasMoreMessages, !isLoadingMore, let cursor = nextCursor else { return }

        isLoadingMore = true

        do {
            let result = try await loadHistoryUseCase.execute(
                sessionId: sessionId,
                cursor: cursor
            )
            // Eski mesajlari basa ekle (kronolojik sira)
            messages.insert(contentsOf: result.messages, at: 0)
            hasMoreMessages = result.hasMore
            nextCursor = result.nextCursor
            logger.info("Ek mesajlar yuklendi: \(result.messages.count) mesaj")
        } catch {
            logger.error("Ek mesaj yukleme hatasi: \(error.localizedDescription)")
        }

        isLoadingMore = false
    }

    /// Streaming mesaj parcasini isler.
    /// - Parameters:
    ///   - messageId: Streaming mesajin ID'si
    ///   - delta: Gelen metin parcasi
    func handleStreamDelta(messageId: String, delta: String) {
        if let index = messages.firstIndex(where: { $0.id == messageId }) {
            let existing = messages[index]
            messages[index] = ChatMessage(
                id: existing.id,
                content: existing.content + delta,
                sender: existing.sender,
                timestamp: existing.timestamp,
                type: existing.type,
                attachments: existing.attachments,
                isStreaming: true
            )
        } else {
            // Yeni streaming mesaj baslat
            let newMessage = ChatMessage(
                id: messageId,
                content: delta,
                sender: .assistant,
                type: .text,
                isStreaming: true
            )
            messages.append(newMessage)
        }
    }

    /// Streaming tamamlandiginda mesaji finalize eder.
    /// - Parameters:
    ///   - messageId: Tamamlanan mesajin ID'si
    ///   - fullText: Tam mesaj icerigi
    ///   - type: Mesaj tipi
    func handleStreamEnd(messageId: String, fullText: String, type: MessageType) {
        if let index = messages.firstIndex(where: { $0.id == messageId }) {
            let existing = messages[index]
            messages[index] = ChatMessage(
                id: existing.id,
                content: fullText,
                sender: existing.sender,
                timestamp: existing.timestamp,
                type: type,
                attachments: existing.attachments,
                isStreaming: false
            )
        }
        isTyping = false
    }

    /// Gelen tam mesaji mesaj listesine ekler.
    func handleIncomingMessage(_ message: ChatMessage) {
        messages.append(message)
        isTyping = false
    }

    /// Typing indicator durumunu gunceller.
    func handleTypingIndicator(isTyping: Bool) {
        self.isTyping = isTyping
    }

    /// Mesaj icerigini panoya kopyalar.
    func copyMessage(_ content: String) {
        UIPasteboard.general.string = content
    }

    /// Hata mesajini temizler.
    func dismissError() {
        errorMessage = nil
    }
}
