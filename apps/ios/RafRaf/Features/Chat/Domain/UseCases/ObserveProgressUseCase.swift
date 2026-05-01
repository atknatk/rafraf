import Foundation

/// Ilerleme durumunu izleme use case'i.
/// WebSocket uzerinden gelen progress event'lerini handle eder.
struct ObserveProgressUseCase: Sendable {
    private let repository: ProgressRepositoryProtocol

    init(repository: ProgressRepositoryProtocol) {
        self.repository = repository
    }

    /// Mevcut ilerleme durumunu getirir.
    /// - Parameter sessionId: Aktif oturum ID'si
    /// - Returns: Mevcut ilerleme durumu
    func execute(sessionId: String) async throws -> ProgressState? {
        try await repository.currentProgress(sessionId: sessionId)
    }

    /// Ilerleme durumunu gunceller.
    /// - Parameters:
    ///   - sessionId: Aktif oturum ID'si
    ///   - state: Yeni ilerleme durumu
    func update(sessionId: String, state: ProgressState) async throws {
        try await repository.updateProgress(sessionId: sessionId, state: state)
    }

    /// Ilerleme durumunu temizler.
    /// - Parameter sessionId: Aktif oturum ID'si
    func clear(sessionId: String) async throws {
        try await repository.clearProgress(sessionId: sessionId)
    }
}
