import Foundation

/// Tum sessionlardan en son N mesaji yukleme use case'i.
/// Home ekraninda son sohbet preview kartini beslemek icin kullanilir.
struct LoadRecentChatUseCase: Sendable {
    private let repository: ChatRepositoryProtocol

    init(repository: ChatRepositoryProtocol) {
        self.repository = repository
    }

    /// - Parameter limit: Donmesi istenen mesaj sayisi (1...20).
    func execute(limit: Int = 1) async throws -> [ChatMessage] {
        let clamped = min(max(limit, 1), 20)
        return try await repository.loadRecent(limit: clamped)
    }
}
