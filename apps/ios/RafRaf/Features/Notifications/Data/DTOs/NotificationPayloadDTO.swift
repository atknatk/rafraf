import Foundation

/// Bildirim ayarlari cevap DTO.
struct NotificationSettingsDTO: Codable, Sendable {
    let taskCompleteEnabled: Bool
    let approvalNeededEnabled: Bool
    let errorEnabled: Bool
    let infoEnabled: Bool
}

/// Bildirim ayarlari guncelleme istegi DTO.
struct NotificationSettingsUpdateDTO: Codable, Sendable {
    let taskCompleteEnabled: Bool?
    let approvalNeededEnabled: Bool?
    let errorEnabled: Bool?
    let infoEnabled: Bool?
}
