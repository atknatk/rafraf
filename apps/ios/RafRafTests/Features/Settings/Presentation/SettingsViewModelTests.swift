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
        let stubUserRepo = StubUserRepository()
        let keychain = KeychainHelper()
        let authManager = AuthManager(keychain: keychain)
        let biometricManager = BiometricAuthManager()
        let vm = SettingsViewModel(
            loadSettingsUseCase: LoadSettingsUseCase(repository: repository),
            saveSettingsUseCase: SaveSettingsUseCase(repository: repository),
            loadProfileUseCase: LoadProfileUseCase(repository: stubUserRepo),
            updateProfileUseCase: UpdateProfileUseCase(repository: stubUserRepo),
            logoutUseCase: LogoutUseCase(authManager: authManager),
            authManager: authManager,
            biometricManager: biometricManager
        )
        return (vm, repository)
    }

    // MARK: - Initial State

    @Test("SettingsViewModel baslangic displayName bos olmali (profil async yuklenir)")
    @MainActor
    func initialDisplayName() {
        let (vm, _) = makeSUT()
        #expect(vm.displayName == "")
    }

    @Test("SettingsViewModel baslangic email bos olmali (profil async yuklenir)")
    @MainActor
    func initialEmail() {
        let (vm, _) = makeSUT()
        #expect(vm.email == "")
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

        #expect(vm.settings.appearance == .dark)
        #expect(vm.settings.fontSize == .large)
    }

    @Test("SettingsViewModel isShowingLogoutConfirmation baslangicta false olmali")
    @MainActor
    func initialLogoutConfirmation() {
        let (vm, _) = makeSUT()
        #expect(vm.isShowingLogoutConfirmation == false)
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
        repository.storedSettings.appearance = .dark
        vm.loadCurrentSettings()

        #expect(vm.settings.appearance == .dark)
        #expect(repository.loadCallCount > initialLoadCount)
    }

    // MARK: - Settings Persistence

    @Test("updateAppearance kaydetme use case'ini tetiklemeli")
    @MainActor
    func updateAppearancePersists() {
        let repository = MockSettingsRepository()
        let (vm, _) = makeSUT(repository: repository)
        let initialSaveCount = repository.saveCallCount

        vm.updateAppearance(.light)

        #expect(repository.saveCallCount > initialSaveCount)
        #expect(repository.lastSavedSettings?.appearance == .light)
    }

    @Test("Birden fazla guncelleme tum degisiklikleri korumali")
    @MainActor
    func multipleUpdatesMaintainAllChanges() {
        let (vm, repository) = makeSUT()

        vm.updateAppearance(.dark)
        vm.updateFontSize(.large)
        vm.updatePushNotifications(false)

        let lastSaved = repository.lastSavedSettings
        #expect(lastSaved?.appearance == .dark)
        #expect(lastSaved?.fontSize == .large)
        #expect(lastSaved?.pushNotificationsEnabled == false)
    }
}

/// Stub user repository for settings tests.
private final class StubUserRepository: UserRepositoryProtocol, @unchecked Sendable {
    func fetchCurrentUser() async throws -> UserProfile {
        UserProfile(id: "stub", displayName: "Stub User", email: "stub@test.com", avatarURL: nil, createdAt: Date())
    }
    func updateDisplayName(_ displayName: String) async throws -> UserProfile {
        UserProfile(id: "stub", displayName: displayName, email: "stub@test.com", avatarURL: nil, createdAt: Date())
    }
    func logout() async throws {}
}
