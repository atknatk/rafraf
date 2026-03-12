import Foundation

/// Proaktif bildirim domain modeli.
/// Backend'den gelen proaktif bildirimin islenmis halidir.
struct ProactiveNotification: Sendable, Identifiable, Equatable {
    /// Benzersiz bildirim ID'si.
    let id: UUID

    /// Bildirim tipi.
    let type: ProactiveNotificationType

    /// Oncelik derecesi.
    let priority: NotificationPriority

    /// Bildirim basligi.
    let title: String

    /// Bildirim govde metni.
    let body: String

    /// Bildirim kaynagi (github, system, ai).
    let source: String

    /// Kaynak event tanimlayicisi (dedup icin).
    let sourceEvent: String?

    /// Deep link URL'si.
    let deepLink: String?

    /// Ek metadata.
    let metadata: [String: String]

    /// Okundu mu.
    let isRead: Bool

    /// Okunma zamani.
    let readAt: Date?

    /// Olusturulma zamani.
    let createdAt: Date
}
