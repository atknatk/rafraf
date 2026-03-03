import Foundation
import os

/// UserDefaults tabanli ayarlar repository implementasyonu.
/// Tum uygulama ayarlarini UserDefaults ile persist eder.
final class SettingsRepositoryImpl: SettingsRepositoryProtocol, @unchecked Sendable {

    // MARK: - Constants

    private enum Keys {
        static let ttsSpeed = "settings.tts.speed"
        static let ttsAutoPlay = "settings.tts.autoPlay"
        static let ttsLanguage = "settings.tts.language"
        static let pushNotificationsEnabled = "settings.notifications.pushEnabled"
        static let enabledNotificationTypes = "settings.notifications.enabledTypes"
        static let appearance = "settings.appearance"
        static let fontSize = "settings.fontSize"
    }

    // MARK: - Private

    private let defaults: UserDefaults
    private let logger = AppLogger.logger(for: "SettingsRepository")

    // MARK: - Init

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
    }

    // MARK: - SettingsRepositoryProtocol

    func loadSettings() -> AppSettings {
        logger.info("Ayarlar yukleniyor")

        let ttsSpeed = defaults.object(forKey: Keys.ttsSpeed) as? Double
            ?? AppSettings.defaults.ttsSpeed
        let ttsAutoPlay = defaults.object(forKey: Keys.ttsAutoPlay) as? Bool
            ?? AppSettings.defaults.ttsAutoPlay
        let ttsLanguageRaw = defaults.string(forKey: Keys.ttsLanguage)
            ?? AppSettings.defaults.ttsLanguage.rawValue
        let pushEnabled = defaults.object(forKey: Keys.pushNotificationsEnabled) as? Bool
            ?? AppSettings.defaults.pushNotificationsEnabled
        let notificationTypesRaw = defaults.stringArray(forKey: Keys.enabledNotificationTypes)
        let appearanceRaw = defaults.string(forKey: Keys.appearance)
            ?? AppSettings.defaults.appearance.rawValue
        let fontSizeRaw = defaults.string(forKey: Keys.fontSize)
            ?? AppSettings.defaults.fontSize.rawValue

        let enabledTypes: Set<NotificationType>
        if let rawTypes = notificationTypesRaw {
            enabledTypes = Set(rawTypes.compactMap { NotificationType(rawValue: $0) })
        } else {
            enabledTypes = AppSettings.defaults.enabledNotificationTypes
        }

        return AppSettings(
            ttsSpeed: ttsSpeed,
            ttsAutoPlay: ttsAutoPlay,
            ttsLanguage: TTSLanguage(rawValue: ttsLanguageRaw)
                ?? AppSettings.defaults.ttsLanguage,
            pushNotificationsEnabled: pushEnabled,
            enabledNotificationTypes: enabledTypes,
            appearance: AppAppearance(rawValue: appearanceRaw)
                ?? AppSettings.defaults.appearance,
            fontSize: AppFontSize(rawValue: fontSizeRaw)
                ?? AppSettings.defaults.fontSize
        )
    }

    func saveSettings(_ settings: AppSettings) {
        logger.info("Ayarlar kaydediliyor")

        defaults.set(settings.ttsSpeed, forKey: Keys.ttsSpeed)
        defaults.set(settings.ttsAutoPlay, forKey: Keys.ttsAutoPlay)
        defaults.set(settings.ttsLanguage.rawValue, forKey: Keys.ttsLanguage)
        defaults.set(settings.pushNotificationsEnabled, forKey: Keys.pushNotificationsEnabled)
        defaults.set(
            settings.enabledNotificationTypes.map(\.rawValue),
            forKey: Keys.enabledNotificationTypes
        )
        defaults.set(settings.appearance.rawValue, forKey: Keys.appearance)
        defaults.set(settings.fontSize.rawValue, forKey: Keys.fontSize)
    }

    func updateSetting<Value: Sendable>(
        _ keyPath: WritableKeyPath<AppSettings, Value>,
        value: Value
    ) {
        var settings = loadSettings()
        settings[keyPath: keyPath] = value
        saveSettings(settings)
    }
}
