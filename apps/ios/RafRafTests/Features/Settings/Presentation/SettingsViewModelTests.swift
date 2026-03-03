import Foundation
import Testing
@testable import RafRaf

/// SettingsViewModel testleri.
@Suite("SettingsViewModel Tests")
struct SettingsViewModelTests {

    // MARK: - Helpers

    @MainActor
    private func makeSUT(
        repository: MockSettingsRepository = MockSettingsRepository()
    ) -> (SettingsViewModel, MockSettingsRepository) {
        let vm = SettingsViewModel(
            loadSettingsUseCase: LoadSettingsUseCase(repository: repository),
            saveSettingsUseCase: SaveSettingsUseCase(repository: repository)
        )
        return (vm, repository)
    }

    // MARK: - Initial State

    @Test("SettingsViewModel baslangic displayName dogru olmali")
    @MainActor
    func initialDisplayName() {
        let (vm, _) = makeSUT()
        #expect(vm.displayName == "RafRaf User")
    }

    @Test("SettingsViewModel baslangic email dogru olmali")
    @MainActor
    func initialEmail() {
        let (vm, _) = makeSUT()
        #expect(vm.email == "user@rafraf.app")
    }

    @Test("SettingsViewModel appVersion bos olmamali")
    @MainActor
    func appVersionNotEmpty() {
        let (vm, _) = makeSUT()
        #expect(!vm.appVersion.isEmpty)
    }

    @Test("SettingsViewModel errorMessage baslangicta nil olmali")
    @MainActor
    func initialErrorMessageNil() {
        let (vm, _) = makeSUT()
        #expect(vm.errorMessage == nil)
    }

    @Test("SettingsViewModel baslangicta ayarlari yuklenmeli")
    @MainActor
    func initialSettingsLoaded() {
        let repository = MockSettingsRepository()
        let (vm, _) = makeSUT(repository: repository)

        #expect(repository.loadCallCount >= 1)
        #expect(vm.settings == AppSettings.defaults)
    }

    @Test("SettingsViewModel ozel ayarlarla baslatildiginda dogru yuklemeli")
    @MainActor
    func initialCustomSettings() {
        let repository = MockSettingsRepository()
        repository.storedSettings = SettingsTestFactory.createCustomSettings()
        let (vm, _) = makeSUT(repository: repository)

        #expect(vm.settings.ttsSpeed == 1.5)
        #expect(vm.settings.appearance == .dark)
        #expect(vm.settings.fontSize == .large)
    }

    @Test("SettingsViewModel isShowingLogoutConfirmation baslangicta false olmali")
    @MainActor
    func initialLogoutConfirmation() {
        let (vm, _) = makeSUT()
        #expect(vm.isShowingLogoutConfirmation == false)
    }

    // MARK: - TTS Speed

    @Test("updateTTSSpeed hizi guncellemeli")
    @MainActor
    func updateTTSSpeed() {
        let (vm, repository) = makeSUT()

        vm.updateTTSSpeed(1.5)

        #expect(vm.settings.ttsSpeed == 1.5)
        #expect(repository.saveCallCount >= 1)
    }

    @Test("updateTTSSpeed alt sinirda clamp etmeli")
    @MainActor
    func updateTTSSpeedClampLow() {
        let (vm, _) = makeSUT()

        vm.updateTTSSpeed(0.1)

        #expect(vm.settings.ttsSpeed == 0.5)
    }

    @Test("updateTTSSpeed ust sinirda clamp etmeli")
    @MainActor
    func updateTTSSpeedClampHigh() {
        let (vm, _) = makeSUT()

        vm.updateTTSSpeed(3.0)

        #expect(vm.settings.ttsSpeed == 2.0)
    }

    @Test("ttsSpeedText dogru formatta olmali")
    @MainActor
    func ttsSpeedText() {
        let (vm, _) = makeSUT()
        vm.updateTTSSpeed(1.5)

        #expect(vm.ttsSpeedText == "1.5x")
    }

    @Test("ttsSpeedText varsayilan hiz icin dogru olmali")
    @MainActor
    func ttsSpeedTextDefault() {
        let (vm, _) = makeSUT()

        #expect(vm.ttsSpeedText == "1.0x")
    }

    // MARK: - TTS AutoPlay

    @Test("updateTTSAutoPlay durumu guncellemeli")
    @MainActor
    func updateTTSAutoPlay() {
        let (vm, repository) = makeSUT()

        vm.updateTTSAutoPlay(true)

        #expect(vm.settings.ttsAutoPlay == true)
        #expect(repository.saveCallCount >= 1)
    }

    @Test("updateTTSAutoPlay false ile kapatmali")
    @MainActor
    func updateTTSAutoPlayOff() {
        let (vm, _) = makeSUT()
        vm.updateTTSAutoPlay(true)

        vm.updateTTSAutoPlay(false)

        #expect(vm.settings.ttsAutoPlay == false)
    }

    // MARK: - TTS Language

    @Test("updateTTSLanguage dili guncellemeli")
    @MainActor
    func updateTTSLanguage() {
        let (vm, repository) = makeSUT()

        vm.updateTTSLanguage(.english)

        #expect(vm.settings.ttsLanguage == .english)
        #expect(repository.saveCallCount >= 1)
    }

    @Test("updateTTSLanguage Turkce'ye geri donebilmeli")
    @MainActor
    func updateTTSLanguageBackToTurkish() {
        let (vm, _) = makeSUT()
        vm.updateTTSLanguage(.english)

        vm.updateTTSLanguage(.turkish)

        #expect(vm.settings.ttsLanguage == .turkish)
    }

    // MARK: - Push Notifications

    @Test("updatePushNotifications durumu guncellemeli")
    @MainActor
    func updatePushNotifications() {
        let (vm, repository) = makeSUT()

        vm.updatePushNotifications(false)

        #expect(vm.settings.pushNotificationsEnabled == false)
        #expect(repository.saveCallCount >= 1)
    }

    // MARK: - Notification Types

    @Test("updateNotificationType tip eklemeli")
    @MainActor
    func updateNotificationTypeAdd() {
        let repository = MockSettingsRepository()
        repository.storedSettings.enabledNotificationTypes = []
        let (vm, _) = makeSUT(repository: repository)

        vm.updateNotificationType(.taskUpdates, enabled: true)

        #expect(vm.settings.enabledNotificationTypes.contains(.taskUpdates))
    }

    @Test("updateNotificationType tip kaldirmali")
    @MainActor
    func updateNotificationTypeRemove() {
        let (vm, _) = makeSUT()

        vm.updateNotificationType(.taskUpdates, enabled: false)

        #expect(!vm.settings.enabledNotificationTypes.contains(.taskUpdates))
    }

    @Test("updateNotificationType birden fazla tip yonetebilmeli")
    @MainActor
    func updateMultipleNotificationTypes() {
        let (vm, _) = makeSUT()

        vm.updateNotificationType(.taskUpdates, enabled: false)
        vm.updateNotificationType(.approvalRequests, enabled: false)

        #expect(!vm.settings.enabledNotificationTypes.contains(.taskUpdates))
        #expect(!vm.settings.enabledNotificationTypes.contains(.approvalRequests))
        #expect(vm.settings.enabledNotificationTypes.contains(.systemAlerts))
    }

    // MARK: - Appearance

    @Test("updateAppearance gorunum modunu guncellemeli")
    @MainActor
    func updateAppearance() {
        let (vm, repository) = makeSUT()

        vm.updateAppearance(.dark)

        #expect(vm.settings.appearance == .dark)
        #expect(repository.saveCallCount >= 1)
    }

    @Test("updateAppearance tum modlar desteklenmeli")
    @MainActor
    func updateAppearanceAllModes() {
        let (vm, _) = makeSUT()

        for mode in AppAppearance.allCases {
            vm.updateAppearance(mode)
            #expect(vm.settings.appearance == mode)
        }
    }

    // MARK: - Font Size

    @Test("updateFontSize boyutu guncellemeli")
    @MainActor
    func updateFontSize() {
        let (vm, repository) = makeSUT()

        vm.updateFontSize(.large)

        #expect(vm.settings.fontSize == .large)
        #expect(repository.saveCallCount >= 1)
    }

    @Test("updateFontSize tum boyutlar desteklenmeli")
    @MainActor
    func updateFontSizeAllSizes() {
        let (vm, _) = makeSUT()

        for size in AppFontSize.allCases {
            vm.updateFontSize(size)
            #expect(vm.settings.fontSize == size)
        }
    }

    // MARK: - Logout

    @Test("showLogoutConfirmation onay dialogunu gostermeli")
    @MainActor
    func showLogoutConfirmation() {
        let (vm, _) = makeSUT()

        vm.showLogoutConfirmation()

        #expect(vm.isShowingLogoutConfirmation == true)
    }

    // MARK: - Load Settings

    @Test("loadCurrentSettings ayarlari yeniden yuklemeli")
    @MainActor
    func loadCurrentSettings() {
        let repository = MockSettingsRepository()
        let (vm, _) = makeSUT(repository: repository)
        let initialLoadCount = repository.loadCallCount

        // Ayarlari degistir ve tekrar yukle
        repository.storedSettings.ttsSpeed = 1.8
        vm.loadCurrentSettings()

        #expect(vm.settings.ttsSpeed == 1.8)
        #expect(repository.loadCallCount > initialLoadCount)
    }

    // MARK: - Settings Persistence

    @Test("updateTTSSpeed kaydetme use case'ini tetiklemeli")
    @MainActor
    func updateTTSSpeedPersists() {
        let repository = MockSettingsRepository()
        let (vm, _) = makeSUT(repository: repository)
        let initialSaveCount = repository.saveCallCount

        vm.updateTTSSpeed(1.3)

        #expect(repository.saveCallCount > initialSaveCount)
        #expect(repository.lastSavedSettings?.ttsSpeed == 1.3)
    }

    @Test("Birden fazla guncelleme tum degisiklikleri korumali")
    @MainActor
    func multipleUpdatesMaintainAllChanges() {
        let (vm, repository) = makeSUT()

        vm.updateTTSSpeed(1.7)
        vm.updateAppearance(.dark)
        vm.updateFontSize(.large)
        vm.updatePushNotifications(false)

        let lastSaved = repository.lastSavedSettings
        #expect(lastSaved?.ttsSpeed == 1.7)
        #expect(lastSaved?.appearance == .dark)
        #expect(lastSaved?.fontSize == .large)
        #expect(lastSaved?.pushNotificationsEnabled == false)
    }
}
