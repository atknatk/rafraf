import Foundation
import os

/// Progress repository implementasyonu.
/// Actor-based in-memory cache ile ilerleme durumlarini yonetir.
final class ProgressRepositoryImpl: ProgressRepositoryProtocol, @unchecked Sendable {
    private let cache = ProgressCache()
    private let logger = AppLogger.logger(for: "ProgressRepository")

    func currentProgress(sessionId: String) async throws -> ProgressState? {
        await cache.get(sessionId: sessionId)
    }

    func updateProgress(sessionId: String, state: ProgressState) async throws {
        await cache.set(sessionId: sessionId, state: state)
        logger.debug("Progress guncellendi - session: \(sessionId), percentage: \(state.percentage)")
    }

    func clearProgress(sessionId: String) async throws {
        await cache.remove(sessionId: sessionId)
        logger.debug("Progress temizlendi - session: \(sessionId)")
    }
}

/// Actor-based progress cache.
/// Thread-safe erisim icin actor kullanilir (NSLock async context'te kullanilamaz).
private actor ProgressCache {
    private var storage: [String: ProgressState] = [:]

    func get(sessionId: String) -> ProgressState? {
        storage[sessionId]
    }

    func set(sessionId: String, state: ProgressState) {
        storage[sessionId] = state
    }

    func remove(sessionId: String) {
        storage.removeValue(forKey: sessionId)
    }
}
