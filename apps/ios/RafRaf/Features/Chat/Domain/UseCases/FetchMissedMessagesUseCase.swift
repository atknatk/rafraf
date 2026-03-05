import Foundation

/// Kacirilmis mesajlari API'den getirir.
/// App arka plandan donunce veya WebSocket reconnect sonrasi kullanilir.
struct FetchMissedMessagesUseCase: Sendable {
    private let repository: ChatRepositoryProtocol

    init(repository: ChatRepositoryProtocol) {
        self.repository = repository
    }

    /// - Parameters:
    ///   - since: ISO 8601 timestamp — bu zamandan sonraki mesajlar
    ///   - sessionId: Oturum ID'si (opsiyonel)
    ///   - projectId: Proje ID'si (opsiyonel)
    func execute(
        since: String,
        sessionId: String? = nil,
        projectId: String? = nil
    ) async throws -> [ChatMessage] {
        try await repository.fetchMissedMessages(
            since: since,
            sessionId: sessionId,
            projectId: projectId
        )
    }
}
