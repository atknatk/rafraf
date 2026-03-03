import Foundation

/// Gelen push bildirimi isleyen use case.
/// Bildirim payload'ini domain modeline donusturur.
struct HandleNotificationUseCase: Sendable {

    /// Bildirim payload'ini domain modeline donusturur.
    /// - Parameter userInfo: APNs bildirim payload dictionary.
    /// - Returns: Islenmis bildirim modeli, gecersiz payload icin nil.
    func execute(userInfo: [String: Any]) -> PushNotification? {
        guard let aps = userInfo["aps"] as? [String: Any] else {
            return nil
        }

        let alert = aps["alert"] as? [String: Any]
        let title = alert?["title"] as? String ?? ""
        let body = alert?["body"] as? String ?? ""
        let badge = aps["badge"] as? Int ?? 0

        let categoryRaw = userInfo["notification_type"] as? String ?? "info"
        let category = NotificationCategory(rawValue: categoryRaw) ?? .info

        let deepLink = userInfo["deep_link"] as? String
        let notificationIdString = userInfo["notification_id"] as? String
        let notificationId = notificationIdString.flatMap { UUID(uuidString: $0) } ?? UUID()

        return PushNotification(
            id: notificationId,
            category: category,
            title: title,
            body: body,
            deepLink: deepLink,
            badgeCount: badge,
            receivedAt: Date()
        )
    }
}
