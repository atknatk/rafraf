import Foundation

/// Mesaj gecmisi yukleme use case'i.
/// Cursor-based pagination ile mesaj gecmisini yukler.
struct LoadChatHistoryUseCase: Sendable {
    private let repository: ChatRepositoryProtocol

    init(repository: ChatRepositoryProtocol) {
        self.repository = repository
    }

    /// Mesaj gecmisini yukler.
    /// - Parameters:
    ///   - sessionId: Oturum ID'si
    ///   - cursor: Sayfalama imleci (nil ise ilk sayfa)
    ///   - limit: Sayfa basina mesaj sayisi (varsayilan: 20)
    /// - Returns: Mesaj listesi ve sayfalama bilgisi
    func execute(
        sessionId: String,
        projectId: String? = nil,
        cursor: String? = nil,
        limit: Int = 20
    ) async throws -> ChatHistoryResult {
        let clampedLimit = min(max(limit, 1), 50)
        return try await repository.loadHistory(
            sessionId: sessionId,
            projectId: projectId,
            cursor: cursor,
            limit: clampedLimit
        )
    }
}
