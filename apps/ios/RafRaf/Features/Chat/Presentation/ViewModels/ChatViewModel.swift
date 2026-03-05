import Foundation
import os
import UIKit

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
    var pendingSuggestions: [String] = []
    var suggestionMessageId: String?
    var messageQueue = MessageQueue()

    // MARK: - Private

    private let sendMessageUseCase: SendMessageUseCase
    private let loadHistoryUseCase: LoadChatHistoryUseCase
    private let fetchMissedMessagesUseCase: FetchMissedMessagesUseCase?
    private let chatRepository: (any ChatRepositoryProtocol)?
    private let sessionId: String
    let projectId: String?
    let agentId: String?
    private var nextCursor: String?
    private var isLoadingMore: Bool = false
    private let logger = AppLogger.logger(for: "Chat")

    /// UserDefaults key — son basarili mesaj timestamp'i.
    private var lastTimestampKey: String {
        "chat_last_message_timestamp_\(sessionId)"
    }

    // MARK: - Init

    init(
        sendMessageUseCase: SendMessageUseCase,
        loadHistoryUseCase: LoadChatHistoryUseCase,
        fetchMissedMessagesUseCase: FetchMissedMessagesUseCase? = nil,
        chatRepository: (any ChatRepositoryProtocol)? = nil,
        sessionId: String = UUID().uuidString,
        projectId: String? = nil,
        agentId: String? = nil
    ) {
        self.sendMessageUseCase = sendMessageUseCase
        self.loadHistoryUseCase = loadHistoryUseCase
        self.fetchMissedMessagesUseCase = fetchMissedMessagesUseCase
        self.chatRepository = chatRepository
        self.sessionId = sessionId
        self.projectId = projectId
        self.agentId = agentId
        logger.info("ChatViewModel baslatildi - session: \(sessionId), project: \(projectId ?? "genel"), agent: \(agentId ?? "none")")
    }

    // MARK: - Actions

    /// Mesaj gonderir.
    /// - Parameter isConnected: WebSocket baglanti durumu. `false` ise mesaj kuyruğa alınır.
    func sendMessage(isConnected: Bool = true) async {
        let text = messageText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }

        messageText = ""

        // Baglanti yoksa kuyruğa al ve bilgi ver
        guard isConnected else {
            messageQueue.enqueue(text: text, projectId: projectId, agentId: agentId)
            errorMessage = String(localized: "chat.queue.queued")
            HapticManager.error()
            logger.info("Cevrimdisi: mesaj kuyruga alindi")
            return
        }

        isSending = true
        errorMessage = nil

        do {
            let sentMessage = try await sendMessageUseCase.execute(
                text: text,
                sessionId: sessionId,
                projectId: projectId,
                agentId: agentId
            )
            HapticManager.messageSent()
            messages.append(sentMessage)
            updateLastMessageTimestamp()
            logger.info("Mesaj gonderildi: \(sentMessage.id)")
        } catch {
            errorMessage = String(localized: "chat.error.sendFailed")
            HapticManager.error()
            logger.error("Mesaj gonderme hatasi: \(error.localizedDescription)")
            // Mesaj metnini geri yukle kullanici tekrar deneyebilsin
            messageText = text
        }

        isSending = false
    }

    /// Baglanti kurulunca bekleyen kuyruklanmis mesajlari gonderir.
    /// WebSocket yeniden baglandiginda cagirilir.
    func flushQueue() async {
        guard !messageQueue.isEmpty else { return }
        let queued = messageQueue.dequeueAll()
        logger.info("Kuyruk bosaltiliyor: \(queued.count) mesaj")
        for msg in queued {
            messageText = msg.text
            await sendMessage(isConnected: true)
        }
    }

    /// Mesaj gecmisini yukler (ilk sayfa).
    func loadHistory() async {
        guard !isLoading else { return }

        isLoading = true
        errorMessage = nil

        do {
            let result = try await loadHistoryUseCase.execute(
                sessionId: sessionId,
                projectId: projectId,
                cursor: nil
            )
            messages = result.messages
            hasMoreMessages = result.hasMore
            nextCursor = result.nextCursor
            updateLastMessageTimestamp()
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
                projectId: projectId,
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
    ///   - tokensUsed: Toplam token sayisi (input + output), varsa
    ///   - modelUsed: Kullanilan model adi, varsa
    func handleStreamEnd(
        messageId: String,
        fullText: String,
        type: MessageType,
        tokensUsed: Int? = nil,
        modelUsed: String? = nil
    ) {
        if let index = messages.firstIndex(where: { $0.id == messageId }) {
            let existing = messages[index]
            messages[index] = ChatMessage(
                id: existing.id,
                content: fullText,
                sender: existing.sender,
                timestamp: existing.timestamp,
                type: type,
                attachments: existing.attachments,
                isStreaming: false,
                tokensUsed: tokensUsed,
                modelUsed: modelUsed
            )
            HapticManager.responseReceived()
        } else if !fullText.isEmpty {
            // Delta gelmeden stream_end gelirse (kısa/hata cevapları) yeni mesaj ekle
            messages.append(ChatMessage(
                id: messageId,
                content: fullText,
                sender: .assistant,
                type: type,
                isStreaming: false,
                tokensUsed: tokensUsed,
                modelUsed: modelUsed
            ))
            updateLastMessageTimestamp()
        }
        isTyping = false
    }

    /// Gelen tam mesaji mesaj listesine ekler.
    func handleIncomingMessage(_ message: ChatMessage) {
        messages.append(message)
        updateLastMessageTimestamp()
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

    /// Gelen code diff mesajini ekler.
    /// - Parameter payload: CodeDiffPayloadDTO JSON icerigi
    func handleCodeDiff(_ payload: CodeDiffPayloadDTO) {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        guard let data = try? encoder.encode(payload),
              let json = String(data: data, encoding: .utf8) else {
            return
        }
        let diffMessage = ChatMessage(
            content: json,
            sender: .assistant,
            type: .codeDiff
        )
        messages.append(diffMessage)
        updateLastMessageTimestamp()
        logger.info("Code diff mesaji eklendi: \(payload.filesChanged) dosya")
    }

    /// Proaktif takip onerilerini gunceller.
    /// - Parameters:
    ///   - messageId: Onerilerle iliskili AI mesajinin ID'si
    ///   - suggestions: Kisa aksiyonable oneri metinleri
    func handleSuggestions(messageId: String, suggestions: [String]) {
        self.suggestionMessageId = messageId
        self.pendingSuggestions = suggestions
    }

    /// Mesaj degerlendirmesi gonderir (thumbs up/down).
    /// Optimistic update yapar; hata durumunda geri alir.
    func rateMessage(id: String, rating: MessageRating) async {
        guard let repo = chatRepository else { return }

        // Optimistic update
        guard let index = messages.firstIndex(where: { $0.id == id }) else { return }
        let original = messages[index]
        let optimistic = ChatMessage(
            id: original.id,
            content: original.content,
            sender: original.sender,
            timestamp: original.timestamp,
            type: original.type,
            attachments: original.attachments,
            isStreaming: original.isStreaming,
            tokensUsed: original.tokensUsed,
            modelUsed: original.modelUsed,
            rating: rating
        )
        messages[index] = optimistic

        do {
            try await repo.rateMessage(id: id, rating: rating)
            logger.info("Mesaj degerlendirmesi basarili: \(id) — \(rating.rawValue)")
        } catch {
            // Hata durumunda geri al
            messages[index] = original
            logger.error("Mesaj degerlendirme hatasi: \(error.localizedDescription)")
        }
    }

    /// Hata mesajini temizler.
    func dismissError() {
        errorMessage = nil
    }

    // MARK: - Missed Messages (Offline Sync)

    /// Kacirilmis mesajlari getirir ve mevcut listeye merge eder.
    /// WebSocket reconnect veya app foreground'a donunce cagirilir.
    func fetchMissedMessages() async {
        guard let useCase = fetchMissedMessagesUseCase else { return }
        guard let since = UserDefaults.standard.string(forKey: lastTimestampKey) else {
            logger.info("lastMessageTimestamp yok, missed messages atlanıyor")
            return
        }

        do {
            let missed = try await useCase.execute(
                since: since,
                sessionId: sessionId,
                projectId: projectId
            )

            guard !missed.isEmpty else { return }

            // Duplicate ID kontrolu ile merge
            let existingIds = Set(messages.map(\.id))
            let newMessages = missed.filter { !existingIds.contains($0.id) }

            if !newMessages.isEmpty {
                messages.append(contentsOf: newMessages)
                messages.sort { $0.timestamp < $1.timestamp }
                updateLastMessageTimestamp()
                logger.info("Kacirilmis mesajlar merge edildi: \(newMessages.count) yeni")
            }
        } catch {
            logger.error("Kacirilmis mesaj fetch hatasi: \(error.localizedDescription)")
        }
    }

    /// Son mesaj timestamp'ini UserDefaults'a kaydeder.
    func updateLastMessageTimestamp() {
        let formatter = ISO8601DateFormatter()
        if let lastMessage = messages.last {
            UserDefaults.standard.set(
                formatter.string(from: lastMessage.timestamp),
                forKey: lastTimestampKey
            )
        }
    }
}
