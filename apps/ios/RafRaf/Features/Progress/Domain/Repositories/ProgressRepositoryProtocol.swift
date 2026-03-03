import Foundation

/// Progress repository protokolu.
/// Domain katmanindan data katmanina erisim saglar.
protocol ProgressRepositoryProtocol: Sendable {
    /// Mevcut ilerleme durumunu dondurur.
    /// - Parameter sessionId: Aktif oturum ID'si
    /// - Returns: Mevcut ilerleme durumu, yoksa nil
    func currentProgress(sessionId: String) async throws -> ProgressState?

    /// Ilerleme durumunu gunceller.
    /// - Parameters:
    ///   - sessionId: Aktif oturum ID'si
    ///   - state: Yeni ilerleme durumu
    func updateProgress(sessionId: String, state: ProgressState) async throws

    /// Ilerleme durumunu temizler.
    /// - Parameter sessionId: Aktif oturum ID'si
    func clearProgress(sessionId: String) async throws
}
