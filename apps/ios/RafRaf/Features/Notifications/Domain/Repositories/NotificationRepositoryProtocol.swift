import Foundation

/// Bildirim repository protokolu.
/// Domain katmani Data katmanindan izole kalir; bu protokol uzerinden iletisir.
protocol NotificationRepositoryProtocol: Sendable {
    /// APNs device token'i backend'e kaydeder.
    /// - Parameter token: APNs device token string'i.
    /// - Returns: Kayit ID'si ve zamani.
    func registerDeviceToken(_ token: String) async throws -> DeviceTokenRegistration

    /// APNs device token'i backend'den siler (logout).
    /// - Parameter token: Silinecek APNs device token.
    func deleteDeviceToken(_ token: String) async throws

    /// Kullanicinin bildirim ayarlarini getirir.
    /// - Returns: Bildirim ayarlari.
    func getNotificationSettings() async throws -> NotificationPreferences

    /// Bildirim ayarlarini gunceller.
    /// - Parameter preferences: Guncellenen ayarlar.
    /// - Returns: Guncellenmis ayarlar.
    func updateNotificationSettings(
        _ preferences: NotificationPreferencesUpdate
    ) async throws -> NotificationPreferences
}

/// Device token kayit sonucu.
struct DeviceTokenRegistration: Sendable, Equatable {
    let id: UUID
    let registeredAt: Date
}

/// Bildirim tercihleri domain modeli.
struct NotificationPreferences: Sendable, Equatable {
    var taskCompleteEnabled: Bool
    var approvalNeededEnabled: Bool
    var errorEnabled: Bool
    var infoEnabled: Bool
}

/// Bildirim tercihleri guncelleme istegi.
struct NotificationPreferencesUpdate: Sendable, Equatable {
    var taskCompleteEnabled: Bool?
    var approvalNeededEnabled: Bool?
    var errorEnabled: Bool?
    var infoEnabled: Bool?
}
