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
        ttsSpeed: Double = 1.5,
        ttsAutoPlay: Bool = true,
        ttsLanguage: TTSLanguage = .english,
        pushNotificationsEnabled: Bool = false,
        enabledNotificationTypes: Set<NotificationType> = [.taskUpdates],
        appearance: AppAppearance = .dark,
        fontSize: AppFontSize = .large
    ) -> AppSettings {
        AppSettings(
            ttsSpeed: ttsSpeed,
            ttsAutoPlay: ttsAutoPlay,
            ttsLanguage: ttsLanguage,
            pushNotificationsEnabled: pushNotificationsEnabled,
            enabledNotificationTypes: enabledNotificationTypes,
            appearance: appearance,
            fontSize: fontSize
        )
    }
}
