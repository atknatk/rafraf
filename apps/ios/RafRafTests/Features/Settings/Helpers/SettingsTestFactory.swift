import Foundation
@testable import RafRaf

/// Settings feature test data factory.
enum SettingsTestFactory {
    /// Varsayilan ayarlar olusturur.
    static func createDefaultSettings() -> AppSettings {
        AppSettings.defaults
    }

    /// Ozel ayarlar olusturur.
    static func createCustomSettings(
        pushNotificationsEnabled: Bool = false,
        enabledNotificationTypes: Set<NotificationType> = [.taskUpdates],
        appearance: AppAppearance = .dark,
        fontSize: AppFontSize = .large
    ) -> AppSettings {
        AppSettings(
            pushNotificationsEnabled: pushNotificationsEnabled,
            enabledNotificationTypes: enabledNotificationTypes,
            appearance: appearance,
            fontSize: fontSize
        )
    }
}
