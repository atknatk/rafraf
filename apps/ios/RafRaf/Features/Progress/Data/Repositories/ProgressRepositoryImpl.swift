import Foundation
import os

/// Progress repository implementasyonu.
/// In-memory cache ile ilerleme durumlarini yonetir.
final class ProgressRepositoryImpl: ProgressRepositoryProtocol, @unchecked Sendable {
    private var progressCache: [String: ProgressState] = [:]
    private let lock = NSLock()
    private let logger = AppLogger.logger(for: "ProgressRepository")

    func currentProgress(sessionId: String) async throws -> ProgressState? {
        lock.lock()
        defer { lock.unlock() }
        return progressCache[sessionId]
    }

    func updateProgress(sessionId: String, state: ProgressState) async throws {
        lock.lock()
        defer { lock.unlock() }
        progressCache[sessionId] = state
        logger.debug("Progress guncellendi - session: \(sessionId), percentage: \(state.percentage)")
    }

    func clearProgress(sessionId: String) async throws {
        lock.lock()
        defer { lock.unlock() }
        progressCache.removeValue(forKey: sessionId)
        logger.debug("Progress temizlendi - session: \(sessionId)")
    }
}
