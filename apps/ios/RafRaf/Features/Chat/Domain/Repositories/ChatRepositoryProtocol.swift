import Foundation

/// Chat repository protokolu.
/// Domain katmani Data katmanindan izole kalir; bu protokol uzerinden iletisir.
protocol ChatRepositoryProtocol: Sendable {
    /// Mesaj gonderir ve gonderilen mesaji dondurur.
    func sendMessage(text: String, sessionId: String, projectId: String?) async throws -> ChatMessage

    /// Mesaj gecmisini yukler (cursor-based pagination).
    /// - Parameters:
    ///   - sessionId: Oturum ID'si
    ///   - cursor: Sayfalama imleci (nil ise ilk sayfa)
    ///   - limit: Sayfa basina mesaj sayisi
    /// - Returns: Mesaj listesi, daha fazla mesaj var mi, sonraki cursor
    func loadHistory(
        sessionId: String,
        cursor: String?,
        limit: Int
    ) async throws -> ChatHistoryResult
}

/// Chat gecmisi sonuc modeli.
struct ChatHistoryResult: Sendable, Equatable {
    let messages: [ChatMessage]
    let hasMore: Bool
    let nextCursor: String?
}
