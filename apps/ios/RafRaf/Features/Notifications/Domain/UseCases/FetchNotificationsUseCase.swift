import Foundation

/// Proaktif bildirim listesini getirme use case'i.
struct FetchNotificationsUseCase: Sendable {
    private let repository: ProactiveNotificationRepositoryProtocol

    init(repository: ProactiveNotificationRepositoryProtocol) {
        self.repository = repository
    }

    /// Bildirimleri getirir.
    /// - Parameters:
    ///   - page: Sayfa numarasi.
    ///   - pageSize: Sayfa basina bildirim sayisi.
    ///   - priority: Oncelik filtresi.
    ///   - isRead: Okunma durumu filtresi.
    ///   - type: Bildirim tipi filtresi.
    /// - Returns: Bildirim listesi sonucu.
    func execute(
        page: Int = 1,
        pageSize: Int = 20,
        priority: NotificationPriority? = nil,
        isRead: Bool? = nil,
        type: ProactiveNotificationType? = nil
    ) async throws -> ProactiveNotificationListResult {
        try await repository.getNotifications(
            page: page,
            pageSize: pageSize,
            priority: priority,
            isRead: isRead,
            type: type
        )
    }
}
