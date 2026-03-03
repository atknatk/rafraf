import Foundation

/// DTO -> Domain model donusumleri.
enum NotificationMapper {
    /// DeviceTokenRegisterResponseDTO -> DeviceTokenRegistration
    static func toDomain(
        _ dto: DeviceTokenRegisterResponseDTO
    ) -> DeviceTokenRegistration {
        DeviceTokenRegistration(
            id: dto.id,
            registeredAt: dto.registeredAt
        )
    }

    /// NotificationSettingsDTO -> NotificationPreferences
    static func toDomain(
        _ dto: NotificationSettingsDTO
    ) -> NotificationPreferences {
        NotificationPreferences(
            taskCompleteEnabled: dto.taskCompleteEnabled,
            approvalNeededEnabled: dto.approvalNeededEnabled,
            errorEnabled: dto.errorEnabled,
            infoEnabled: dto.infoEnabled
        )
    }

    /// NotificationPreferencesUpdate -> NotificationSettingsUpdateDTO
    static func toDTO(
        _ update: NotificationPreferencesUpdate
    ) -> NotificationSettingsUpdateDTO {
        NotificationSettingsUpdateDTO(
            taskCompleteEnabled: update.taskCompleteEnabled,
            approvalNeededEnabled: update.approvalNeededEnabled,
            errorEnabled: update.errorEnabled,
            infoEnabled: update.infoEnabled
        )
    }
}
