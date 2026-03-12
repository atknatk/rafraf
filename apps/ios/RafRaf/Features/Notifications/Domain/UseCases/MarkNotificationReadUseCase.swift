import Foundation

/// Bildirimi okundu olarak isaretleme use case'i.
struct MarkNotificationReadUseCase: Sendable {
    private let repository: ProactiveNotificationRepositoryProtocol

    init(repository: ProactiveNotificationRepositoryProtocol) {
        self.repository = repository
    }

    /// Tek bir bildirimi okundu isaretle.
    /// - Parameter notificationId: Bildirim ID'si.
    /// - Returns: Guncellenmis bildirim.
    func execute(notificationId: UUID) async throws -> ProactiveNotification {
        try await repository.markAsRead(notificationId: notificationId)
    }

    /// Tum bildirimleri okundu isaretle.
    /// - Returns: Isaretlenen bildirim sayisi.
    func executeAll() async throws -> Int {
        try await repository.markAllAsRead()
    }
}
