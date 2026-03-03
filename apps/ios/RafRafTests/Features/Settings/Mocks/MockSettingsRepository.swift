import Foundation
@testable import RafRaf

/// Test icin mock settings repository.
final class MockSettingsRepository: SettingsRepositoryProtocol, @unchecked Sendable {
    var storedSettings: AppSettings = .defaults
    var loadCallCount = 0
    var saveCallCount = 0
    var updateCallCount = 0
    var lastSavedSettings: AppSettings?

    func loadSettings() -> AppSettings {
        loadCallCount += 1
        return storedSettings
    }

    func saveSettings(_ settings: AppSettings) {
        saveCallCount += 1
        lastSavedSettings = settings
        storedSettings = settings
    }

    func updateSetting<Value: Sendable>(
        _ keyPath: WritableKeyPath<AppSettings, Value>,
        value: Value
    ) {
        updateCallCount += 1
        storedSettings[keyPath: keyPath] = value
    }
}
