import Foundation

/// Proaktif bildirim repository protokolu.
/// Domain katmani Data katmanindan izole kalir; bu protokol uzerinden iletisir.
protocol ProactiveNotificationRepositoryProtocol: Sendable {
    /// Proaktif bildirim listesini getirir.
    /// - Parameters:
    ///   - page: Sayfa numarasi.
    ///   - pageSize: Sayfa basina bildirim sayisi.
    ///   - priority: Oncelik filtresi (opsiyonel).
    ///   - isRead: Okunma durumu filtresi (opsiyonel).
    ///   - type: Bildirim tipi filtresi (opsiyonel).
    /// - Returns: Bildirim listesi ve toplam sayi.
    func getNotifications(
        page: Int,
        pageSize: Int,
        priority: NotificationPriority?,
        isRead: Bool?,
        type: ProactiveNotificationType?
    ) async throws -> ProactiveNotificationListResult

    /// Bildirimi okundu olarak isaretle.
    /// - Parameter notificationId: Bildirim ID'si.
    /// - Returns: Guncellenmis bildirim.
    func markAsRead(notificationId: UUID) async throws -> ProactiveNotification

    /// Tum bildirimleri okundu isaretle.
    /// - Returns: Isaretlenen bildirim sayisi.
    func markAllAsRead() async throws -> Int

    /// Bildirimi sil.
    /// - Parameter notificationId: Bildirim ID'si.
    func deleteNotification(notificationId: UUID) async throws

    /// Okunmamis bildirim sayisini getirir.
    /// - Returns: Okunmamis bildirim sayisi.
    func getUnreadCount() async throws -> Int
}

/// Proaktif bildirim listesi sonucu.
struct ProactiveNotificationListResult: Sendable, Equatable {
    let notifications: [ProactiveNotification]
    let total: Int
    let page: Int
    let pageSize: Int
}
