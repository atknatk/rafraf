import Foundation
import os
import UIKit

// MARK: - Tool Activity Models

/// Tek bir arac calistirma adimi (inline aktivite karti icin).
struct ToolStep: Sendable, Identifiable {
    let id: String
    let label: String
    let status: String  // "active", "completed", "failed"
    let detail: String?
    let durationSeconds: Double?

    var sfIcon: String {
        switch status {
        case "completed": return "checkmark.circle.fill"
        case "failed": return "xmark.circle.fill"
        default: return "circle"
        }
    }
}

/// Aktif AI calisma durumu — inline aktivite karti icin.
struct ToolActivityModel: Sendable {
    let phase: String
    let phaseLabel: String
    let percentage: Int
    let steps: [ToolStep]

    var isCompleted: Bool { phase == "completed" }
    var isActive: Bool { !["completed", ""].contains(phase) }
}

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
    /// Aktif AI calisma durumu — inline tool aktivite karti icin.
    var currentActivity: ToolActivityModel?

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

    // MARK: - Stream Delta Coalescing
    //
    // PERFORMANCE: Claude per-token deltas arrive at hundreds of chunks per
    // second. Mutating `messages[idx]` for each chunk triggers full Observable
    // invalidation + SwiftUI diff over the entire bubble tree, plus an O(n^2)
    // string concat cost on long responses (~10^8 char copies for a 100KB
    // assistant message). We coalesce all deltas that arrive within a single
    // 60Hz display frame (~16ms) into one `messages[idx]` mutation per
    // message_id. Authoritative content is verified against `chat.stream_end`
    // `full_text` (see `handleStreamEnd`).
    //
    // Approach: parallel `[messageId: String]` buffer. Avoids changing the
    // immutable `ChatMessage` struct shape (no `var content` refactor) and
    // SwiftUI sees a single content change per frame instead of per token.

    /// Per-message-id accumulated delta buffer waiting to be flushed.
    private var streamBuffers: [String: String] = [:]
    /// Currently scheduled flush task (16ms window). `nil` when no flush pending.
    private var flushTask: Task<Void, Never>?
    /// Configurable flush window — 16ms = one display frame at 60Hz.
    /// Exposed `internal` for tests; production code does not override.
    let streamFlushInterval: Duration

    // MARK: - Diagnostics (testing only)

    /// Number of times `messages[idx]` has been mutated due to stream delta flush.
    /// Tests use this to verify coalescing behaviour. Production code never reads it.
    private(set) var streamFlushCount: Int = 0

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
        agentId: String? = nil,
        streamFlushInterval: Duration = .milliseconds(16)
    ) {
        self.sendMessageUseCase = sendMessageUseCase
        self.loadHistoryUseCase = loadHistoryUseCase
        self.fetchMissedMessagesUseCase = fetchMissedMessagesUseCase
        self.chatRepository = chatRepository
        self.sessionId = sessionId
        self.projectId = projectId
        self.agentId = agentId
        self.streamFlushInterval = streamFlushInterval
        logger.info("ChatViewModel baslatildi - session: \(sessionId), project: \(projectId ?? "genel"), agent: \(agentId ?? "none")")
    }

    // NOTE: `flushTask` deliberately not cancelled in `deinit` — it is `@MainActor`
    // isolated and Swift 6 prohibits cross-isolation access from nonisolated deinit.
    // The task captures `[weak self]`; once self deallocates, the closure becomes
    // a safe no-op (no double-trigger, no leak — Task is single-shot).

    // MARK: - Actions

    /// Mesaj gonderir.
    /// - Parameter isConnected: WebSocket baglanti durumu. `false` ise mesaj kuyruğa alınır.
    func sendMessage(isConnected: Bool = true) async {
        let text = messageText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }

        // isSending'i messageText temizlemeden ONCE set et
        // Aksi halde actionButton send→mic gecisi ayni tap'i yakalar
        isSending = true
        messageText = ""

        // Baglanti yoksa kuyruğa al ve bilgi ver
        guard isConnected else {
            messageQueue.enqueue(text: text, projectId: projectId, agentId: agentId)
            errorMessage = String(localized: "chat.queue.queued")
            HapticManager.error()
            logger.info("Cevrimdisi: mesaj kuyruga alindi")
            isSending = false
            return
        }

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
    /// Mevcut mesajlarla ID bazli dedup yaparak birlestirir (reconnect duplicate onleme).
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

            if messages.isEmpty {
                // Ilk yukleme — direkt ata
                messages = result.messages
            } else {
                // Reconnect/refresh — ID bazli dedup ile merge
                let existingIds = Set(messages.map(\.id))
                let newMessages = result.messages.filter { !existingIds.contains($0.id) }
                if !newMessages.isEmpty {
                    messages.append(contentsOf: newMessages)
                    messages.sort { $0.timestamp < $1.timestamp }
                }
            }

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
    ///
    /// Delta'lar bir 16ms penceresine coalesce edilir — `messages[idx]` mutasyonu
    /// frame basina en fazla bir kez tetiklenir (bkz. `streamFlushInterval`,
    /// `flushStreamBuffersIfNeeded`). Bu sayede 100KB'lik bir cevap icin
    /// O(n^2) string concat ve 1000+ Observable invalidasyonu yerine
    /// frame basina tek mutasyon olur.
    ///
    /// - Parameters:
    ///   - messageId: Streaming mesajin ID'si
    ///   - delta: Gelen metin parcasi
    func handleStreamDelta(messageId: String, delta: String) {
        // Mesaj henuz listede yoksa (ilk delta) bos placeholder olustur ki
        // sonraki flush in-place mutasyonu calissin. Bu append uniktir, bir
        // mesaj basina sadece bir kez calisir.
        if !messages.contains(where: { $0.id == messageId }) {
            let placeholder = ChatMessage(
                id: messageId,
                content: "",
                sender: .assistant,
                type: .text,
                isStreaming: true
            )
            messages.append(placeholder)
        }

        // Tek string append — Swift COW ile bos buffer'a ilk yazimda allocate;
        // sonrasinda exclusive olunca String.append amortize O(1).
        streamBuffers[messageId, default: ""] += delta

        scheduleFlushIfNeeded()
    }

    /// 16ms gecikmeli flush'i programlar; zaten programlanmis ise no-op.
    private func scheduleFlushIfNeeded() {
        guard flushTask == nil else { return }
        let interval = streamFlushInterval
        flushTask = Task { [weak self] in
            try? await Task.sleep(for: interval)
            guard !Task.isCancelled else { return }
            await MainActor.run {
                self?.flushTask = nil
                self?.flushStreamBuffers()
            }
        }
    }

    /// Buffer'da bekleyen tum delta'lari ilgili `messages[idx]`'lere uygular.
    /// Her message_id icin tam olarak BIR `messages[idx]` mutasyonu yapilir
    /// (Swift COW + tek append => String level minimum allocation).
    private func flushStreamBuffers() {
        guard !streamBuffers.isEmpty else { return }
        let pending = streamBuffers
        streamBuffers.removeAll(keepingCapacity: true)

        for (messageId, accumulated) in pending where !accumulated.isEmpty {
            guard let index = messages.firstIndex(where: { $0.id == messageId }) else {
                // Mesaj kaybolmus (ornek: stream_end finalize sonrasi gec gelen
                // delta) — sessizce dus.
                continue
            }
            let existing = messages[index]
            // Whole-struct replace (let-only ChatMessage) — ama frame basina
            // sadece BIR kez. Eski koddaki per-token mutation'a gore O(n) -> O(1)
            // SwiftUI invalidasyon kazanci.
            messages[index] = ChatMessage(
                id: existing.id,
                content: existing.content + accumulated,
                sender: existing.sender,
                timestamp: existing.timestamp,
                type: existing.type,
                attachments: existing.attachments,
                isStreaming: true
            )
            streamFlushCount += 1
        }
    }

    /// Bekleyen flush'i iptal eder ve buffer'i hemen senkron uygular.
    /// `handleStreamEnd` icin: stream_end geldiginde buffered delta'larin
    /// finalizasyondan once mesaja yansimasini garanti eder.
    private func forceFlushStreamBuffers() {
        flushTask?.cancel()
        flushTask = nil
        flushStreamBuffers()
    }

    /// Test-only — buffered delta'lari senkron uygulamak icin.
    /// Production kodu `flushTask`'in 16ms tetigine guvenir; testler ise
    /// non-deterministic sleep'lerden kacinmak icin bu helper'i cagirir.
    func flushPendingStreamDeltasForTesting() {
        forceFlushStreamBuffers()
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
        // Bekleyen delta'lari hemen uygula — `fullText` authoritative kontrat
        // olsa da observability ve test acisindan coalesced state'in tam olmasi
        // gerekir. Sonrasinda `fullText` ile finalize ediyoruz, dolayisi ile
        // bu adim functional olarak overwrite ediliyor; ancak buffered residue
        // birakmamak icin onemli (memory leak / sonraki mesajla karismayi onler).
        forceFlushStreamBuffers()

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
        currentActivity = nil
    }

    /// Gelen tam mesaji mesaj listesine ekler (ID bazli dedup).
    func handleIncomingMessage(_ message: ChatMessage) {
        guard !messages.contains(where: { $0.id == message.id }) else { return }
        messages.append(message)
        updateLastMessageTimestamp()
        isTyping = false
    }

    /// Typing indicator durumunu gunceller.
    func handleTypingIndicator(isTyping: Bool) {
        self.isTyping = isTyping
        if !isTyping {
            // Typing durdu — aktivite bilgisini temizle
            currentActivity = nil
        }
    }

    /// Progress event'ini isler — inline tool aktivite kartini gunceller.
    func handleProgress(_ content: ProgressMessageContent) {
        let steps = (content.stepsDetail ?? []).map { step in
            ToolStep(
                id: step.id,
                label: step.label,
                status: step.status,
                detail: step.detail,
                durationSeconds: step.durationSeconds
            )
        }
        currentActivity = ToolActivityModel(
            phase: content.phase ?? "starting",
            phaseLabel: content.task,
            percentage: content.percentage,
            steps: steps
        )
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
