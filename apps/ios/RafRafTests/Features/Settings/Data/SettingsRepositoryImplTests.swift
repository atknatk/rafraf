import Foundation
import Testing
@testable import RafRaf

/// SettingsRepositoryImpl testleri.
/// UserDefaults tabanli ayar persistansini test eder.
@Suite("SettingsRepositoryImpl Tests")
struct SettingsRepositoryImplTests {

    // MARK: - Helpers

    /// Her test icin izole UserDefaults olusturur.
    private func makeRepository() -> (SettingsRepositoryImpl, UserDefaults) {
        let suiteName = "test.settings.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suiteName)!
        let repository = SettingsRepositoryImpl(defaults: defaults)
        return (repository, defaults)
    }

    // MARK: - Load

    @Test("loadSettings bos defaults ile varsayilan degerleri donmeli")
    func loadReturnsDefaults() {
        let (repository, _) = makeRepository()

        let settings = repository.loadSettings()

        #expect(settings.ttsSpeed == AppSettings.defaults.ttsSpeed)
        #expect(settings.ttsAutoPlay == AppSettings.defaults.ttsAutoPlay)
        #expect(settings.ttsLanguage == AppSettings.defaults.ttsLanguage)
        #expect(settings.pushNotificationsEnabled == AppSettings.defaults.pushNotificationsEnabled)
        #expect(settings.appearance == AppSettings.defaults.appearance)
        #expect(settings.fontSize == AppSettings.defaults.fontSize)
    }

    // MARK: - Save & Load Roundtrip

    @Test("saveSettings ve loadSettings roundtrip dogru calismali")
    func saveAndLoadRoundtrip() {
        let (repository, _) = makeRepository()
        let customSettings = SettingsTestFactory.createCustomSettings()

        repository.saveSettings(customSettings)
        let loaded = repository.loadSettings()

        #expect(loaded.ttsSpeed == customSettings.ttsSpeed)
        #expect(loaded.ttsAutoPlay == customSettings.ttsAutoPlay)
        #expect(loaded.ttsLanguage == customSettings.ttsLanguage)
        #expect(loaded.pushNotificationsEnabled == customSettings.pushNotificationsEnabled)
        #expect(loaded.enabledNotificationTypes == customSettings.enabledNotificationTypes)
        #expect(loaded.appearance == customSettings.appearance)
        #expect(loaded.fontSize == customSettings.fontSize)
    }

    @Test("saveSettings varsayilan ayarlarla roundtrip dogru calismali")
    func saveDefaultsRoundtrip() {
        let (repository, _) = makeRepository()

        repository.saveSettings(.defaults)
        let loaded = repository.loadSettings()

        #expect(loaded == AppSettings.defaults)
    }

    // MARK: - Individual Fields

    @Test("saveSettings TTS hiz degerini dogru kaydetmeli")
    func saveTTSSpeed() {
        let (repository, _) = makeRepository()
        var settings = AppSettings.defaults
        settings.ttsSpeed = 1.8

        repository.saveSettings(settings)
        let loaded = repository.loadSettings()

        #expect(loaded.ttsSpeed == 1.8)
    }

    @Test("saveSettings gorunum modunu dogru kaydetmeli")
    func saveAppearance() {
        let (repository, _) = makeRepository()
        var settings = AppSettings.defaults
        settings.appearance = .dark

        repository.saveSettings(settings)
        let loaded = repository.loadSettings()

        #expect(loaded.appearance == .dark)
    }

    @Test("saveSettings font boyutunu dogru kaydetmeli")
    func saveFontSize() {
        let (repository, _) = makeRepository()
        var settings = AppSettings.defaults
        settings.fontSize = .large

        repository.saveSettings(settings)
        let loaded = repository.loadSettings()

        #expect(loaded.fontSize == .large)
    }

    @Test("saveSettings bildirim tiplerini dogru kaydetmeli")
    func saveNotificationTypes() {
        let (repository, _) = makeRepository()
        var settings = AppSettings.defaults
        settings.enabledNotificationTypes = [.taskUpdates, .systemAlerts]

        repository.saveSettings(settings)
        let loaded = repository.loadSettings()

        #expect(loaded.enabledNotificationTypes.contains(.taskUpdates))
        #expect(loaded.enabledNotificationTypes.contains(.systemAlerts))
        #expect(!loaded.enabledNotificationTypes.contains(.approvalRequests))
    }

    @Test("saveSettings bos bildirim tipleri dogru kaydetmeli")
    func saveEmptyNotificationTypes() {
        let (repository, _) = makeRepository()
        var settings = AppSettings.defaults
        settings.enabledNotificationTypes = []

        repository.saveSettings(settings)
        let loaded = repository.loadSettings()

        #expect(loaded.enabledNotificationTypes.isEmpty)
    }

    // MARK: - updateSetting

    @Test("updateSetting tek bir alani guncellemeli")
    func updateSingleField() {
        let (repository, _) = makeRepository()

        repository.updateSetting(\.ttsSpeed, value: 0.7)
        let loaded = repository.loadSettings()

        #expect(loaded.ttsSpeed == 0.7)
        // Diger degerler varsayilan kalmali
        #expect(loaded.appearance == AppSettings.defaults.appearance)
    }

    @Test("updateSetting gorunum modunu guncellemeli")
    func updateAppearance() {
        let (repository, _) = makeRepository()

        repository.updateSetting(\.appearance, value: .light)
        let loaded = repository.loadSettings()

        #expect(loaded.appearance == .light)
    }

    // MARK: - Invalid Data Handling

    @Test("loadSettings gecersiz rawValue icin varsayilan donmeli")
    func loadWithInvalidRawValues() {
        let suiteName = "test.settings.invalid.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suiteName)!
        defaults.set("invalid_appearance", forKey: "settings.appearance")
        defaults.set("invalid_language", forKey: "settings.tts.language")
        defaults.set("invalid_font", forKey: "settings.fontSize")

        let repository = SettingsRepositoryImpl(defaults: defaults)
        let loaded = repository.loadSettings()

        #expect(loaded.appearance == AppSettings.defaults.appearance)
        #expect(loaded.ttsLanguage == AppSettings.defaults.ttsLanguage)
        #expect(loaded.fontSize == AppSettings.defaults.fontSize)
    }
}
