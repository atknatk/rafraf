import Foundation
import os

/// `SessionTitleRepositoryProtocol` in-memory + broadcast implementasyonu.
///
/// WebSocket router'dan gelen her `SessionTitleContent` mesaji `handle(content:)`
/// uzerinden bu repository'ye dusuyor; repository tum aboneler icin AsyncStream
/// uretir ve son durumu (sessionId → update) cache'ler. Boylece geç abone olan
/// view model en son durumu `snapshot()` ile alip baslik gosterimini dogru
/// rendelayebilir.
///
/// Notlar:
/// - Persistence (UserDefaults vs.) bu surumde devre disi. Mevcut Home oturumu
///   listesi henuz UI'da yok; uretici kaynak baglandiginda ihtiyaca gore
///   eklenecek.
/// - Aktor: Concurrency safety icin `actor` kullanildi; AsyncStream
///   continuation'lari `nonisolated(unsafe)` olmadan dogru sahiplik altinda
///   tutulur.
actor SessionTitleRepositoryImpl: SessionTitleRepositoryProtocol {
    // MARK: - State

    /// Aktif aboneler icin yield edilen continuation listesi.
    /// Token (UUID) abonelik biter bitmez `onTermination` ile remove edilir.
    private var continuations: [UUID: AsyncStream<SessionTitleUpdate>.Continuation] = [:]

    /// SessionId → en son update cache'i.
    private var cache: [String: SessionTitleUpdate] = [:]

    private nonisolated let logger = Logger(
        subsystem: "com.rafraf",
        category: "SessionTitleRepository"
    )

    // MARK: - Init

    init() {}

    // MARK: - SessionTitleRepositoryProtocol

    nonisolated func titleUpdates() -> AsyncStream<SessionTitleUpdate> {
        AsyncStream { continuation in
            let token = UUID()
            Task { [weak self] in
                await self?.subscribe(token: token, continuation: continuation)
            }
            continuation.onTermination = { [weak self] _ in
                Task { [weak self] in
                    await self?.unsubscribe(token: token)
                }
            }
        }
    }

    func snapshot() async -> [String: SessionTitleUpdate] {
        cache
    }

    // MARK: - Producer API

    /// Router'dan gelen `SessionTitleContent` mesajini map edip emit eder.
    /// - Parameter content: WebSocket payload (T1.6).
    func handle(content: SessionTitleContent) {
        let update = SessionTitleMapper.toDomain(content)
        emit(update)
    }

    /// Hazir bir `SessionTitleUpdate` emit eder (test ve replay icin).
    /// - Parameter update: Yayilacak guncelleme.
    func emit(_ update: SessionTitleUpdate) {
        cache[update.sessionId] = update
        for (_, continuation) in continuations {
            continuation.yield(update)
        }
        logger.info(
            "ai-title yayildi sessionId=\(update.sessionId, privacy: .public) abone=\(self.continuations.count, privacy: .public)"
        )
    }

    // MARK: - Subscriber Lifecycle

    private func subscribe(
        token: UUID,
        continuation: AsyncStream<SessionTitleUpdate>.Continuation
    ) {
        continuations[token] = continuation
        // Replay: yeni abone son durumu hemen alabilsin.
        for update in cache.values {
            continuation.yield(update)
        }
        logger.debug("Yeni session.title abonesi: \(token.uuidString, privacy: .public)")
    }

    private func unsubscribe(token: UUID) {
        continuations.removeValue(forKey: token)
        logger.debug("session.title abonesi kaldirildi: \(token.uuidString, privacy: .public)")
    }
}
