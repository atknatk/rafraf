import Foundation

/// Mesaj gonderme use case'i.
/// Business logic: Bos mesaj kontrolu, karakter limiti, gonderme islemi.
struct SendMessageUseCase: Sendable {
    private let repository: ChatRepositoryProtocol

    init(repository: ChatRepositoryProtocol) {
        self.repository = repository
    }

    /// Mesaj gonderir.
    /// - Parameters:
    ///   - text: Mesaj metni (1-4096 karakter)
    ///   - sessionId: Aktif oturum ID'si
    /// - Returns: Gonderilen mesaj
    /// - Throws: Bos mesaj veya karakter limiti asildiginda hata
    func execute(text: String, sessionId: String) async throws -> ChatMessage {
        let trimmedText = text.trimmingCharacters(in: .whitespacesAndNewlines)

        guard !trimmedText.isEmpty else {
            throw SendMessageError.emptyMessage
        }

        guard trimmedText.count <= 4096 else {
            throw SendMessageError.messageTooLong(count: trimmedText.count, limit: 4096)
        }

        return try await repository.sendMessage(text: trimmedText, sessionId: sessionId)
    }
}

/// Mesaj gonderme hatalari.
enum SendMessageError: Error, Sendable, Equatable {
    case emptyMessage
    case messageTooLong(count: Int, limit: Int)
}
