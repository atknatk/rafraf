import Foundation

/// Push bildirim domain modeli.
/// Gelen bildirimin islenmis halidir.
struct PushNotification: Sendable, Identifiable, Equatable {
    /// Benzersiz bildirim ID'si.
    let id: UUID

    /// Bildirim kategorisi.
    let category: NotificationCategory

    /// Bildirim basligi.
    let title: String

    /// Bildirim govde metni.
    let body: String

    /// Deep link URL string'i (orn. "rafraf://chat/session_id").
    let deepLink: String?

    /// Okunmamis bildirim sayisi (badge).
    let badgeCount: Int

    /// Bildirimin alindigi zaman.
    let receivedAt: Date
}
