import Foundation

/// Chat repository protokolu.
/// Domain katmani Data katmanindan izole kalir; bu protokol uzerinden iletisir.
protocol ChatRepositoryProtocol: Sendable {
    /// Belirtilen proje icin mesajlari getirir.
    func fetchMessages(projectId: String) async throws -> [ChatMessage]

    /// Mesaj gonderir.
    func sendMessage(projectId: String, content: String, type: MessageType) async throws -> ChatMessage
}
