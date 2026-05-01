import Foundation
import os

/// Ayarlar ViewModel.
/// Settings ekraninin durumunu ve islemlerini yonetir.
/// Bildirim, gorunum ve hesap ayarlarini yonetir.
@Observable
@MainActor
final class SettingsViewModel {
    // MARK: - State

    /// Kullanici goruntu adi.
    var displayName: String = ""

    /// Kullanici e-posta adresi.
    var email: String = ""

    /// Profil yukleniyor mu.
    var isLoadingProfile: Bool = false

    /// Profil duzenleme sheet'i gosteriliyor mu.
    var isShowingProfileEdit: Bool = false

    /// Duzenlenen goruntu adi.
    var editingDisplayName: String = ""

    /// Hata mesaji.
    var errorMessage: String?

    /// Mevcut uygulama ayarlari.
    var settings: AppSettings = .defaults

    /// Cikis onay dialogu gosteriliyor mu.
    var isShowingLogoutConfirmation: Bool = false

    // MARK: - Computed

    /// Uygulama versiyonu.
    var appVersion: String {
        let version = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "1.0"
        let build = Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? "1"
        return "\(version) (\(build))"
    }

    // MARK: - Private

    private let loadSettingsUseCase: LoadSettingsUseCase
    private let saveSettingsUseCase: SaveSettingsUseCase
    private let loadProfileUseCase: LoadProfileUseCase
    private let updateProfileUseCase: UpdateProfileUseCase
    private let logoutUseCase: LogoutUseCase
    private let authManager: AuthManager
    private let biometricManager: BiometricAuthManager
    private let logger = AppLogger.logger(for: "Settings")

    // MARK: - Computed

    /// Biyometrik dogrulama cihazda mevcut mu.
    var isBiometricAvailable: Bool {
        biometricManager.isBiometricAvailable
    }

    /// Biyometrik dogrulama aktif mi.
    var isBiometricEnabled: Bool {
        authManager.isBiometricEnabled
    }

    // MARK: - Init

    init(
        loadSettingsUseCase: LoadSettingsUseCase,
        saveSettingsUseCase: SaveSettingsUseCase,
        loadProfileUseCase: LoadProfileUseCase,
        updateProfileUseCase: UpdateProfileUseCase,
        logoutUseCase: LogoutUseCase,
        authManager: AuthManager,
        biometricManager: BiometricAuthManager
    ) {
        self.loadSettingsUseCase = loadSettingsUseCase
        self.saveSettingsUseCase = saveSettingsUseCase
        self.loadProfileUseCase = loadProfileUseCase
        self.updateProfileUseCase = updateProfileUseCase
        self.logoutUseCase = logoutUseCase
        self.authManager = authManager
        self.biometricManager = biometricManager
        logger.info("SettingsViewModel baslatildi")
        loadCurrentSettings()
    }

    // MARK: - Actions

    /// Ayarlari yukler.
    func loadCurrentSettings() {
        settings = loadSettingsUseCase.execute()
        logger.info("Ayarlar yuklendi")
    }

    /// Profili API'den yukler.
    func loadProfile() async {
        isLoadingProfile = true
        do {
            let profile = try await loadProfileUseCase.execute()
            displayName = profile.displayName
            email = profile.email
            logger.info("Profil yuklendi: \(profile.displayName)")
        } catch {
            logger.error("Profil yukleme hatasi: \(error.localizedDescription)")
            errorMessage = String(localized: "settings.profile.loadError")
        }
        isLoadingProfile = false
    }

    /// Profil duzenleme sheet'ini acar.
    func showProfileEdit() {
        editingDisplayName = displayName
        isShowingProfileEdit = true
    }

    /// Goruntu adini gunceller.
    func saveProfileChanges() async {
        guard !editingDisplayName.trimmingCharacters(in: .whitespaces).isEmpty else { return }
        do {
            let updated = try await updateProfileUseCase.execute(displayName: editingDisplayName)
            displayName = updated.displayName
            isShowingProfileEdit = false
            logger.info("Profil guncellendi: \(updated.displayName)")
        } catch {
            logger.error("Profil guncelleme hatasi: \(error.localizedDescription)")
            errorMessage = String(localized: "settings.profile.updateError")
        }
    }

    /// Push bildirim durumunu degistirir.
    /// - Parameter enabled: Aktif mi.
    func updatePushNotifications(_ enabled: Bool) {
        settings.pushNotificationsEnabled = enabled
        saveCurrentSettings()
        logger.info("Push bildirimler guncellendi: \(enabled)")
    }

    /// Bildirim tipini aktif/pasif yapar.
    /// - Parameters:
    ///   - type: Bildirim tipi.
    ///   - enabled: Aktif mi.
    func updateNotificationType(_ type: NotificationType, enabled: Bool) {
        if enabled {
            settings.enabledNotificationTypes.insert(type)
        } else {
            settings.enabledNotificationTypes.remove(type)
        }
        saveCurrentSettings()
        logger.info("Bildirim tipi guncellendi: \(type.rawValue) = \(enabled)")
    }

    /// Gorunum modunu degistirir.
    /// - Parameter appearance: Yeni gorunum modu.
    func updateAppearance(_ appearance: AppAppearance) {
        settings.appearance = appearance
        saveCurrentSettings()
        logger.info("Gorunum modu guncellendi: \(appearance.rawValue)")
    }

    /// Font boyutunu degistirir.
    /// - Parameter fontSize: Yeni font boyutu.
    func updateFontSize(_ fontSize: AppFontSize) {
        settings.fontSize = fontSize
        saveCurrentSettings()
        logger.info("Font boyutu guncellendi: \(fontSize.rawValue)")
    }

    /// Biyometrik dogrulama tercihini gunceller.
    /// - Parameter enabled: Aktif mi.
    func updateBiometricEnabled(_ enabled: Bool) {
        authManager.setBiometricEnabled(enabled)
        logger.info("Biyometrik tercih guncellendi: \(enabled)")
    }

    /// Cikis onay dialogunu gosterir.
    func showLogoutConfirmation() {
        isShowingLogoutConfirmation = true
    }

    /// Cikis yapar.
    func logout() async {
        logger.info("Cikis yapiliyor")
        logoutUseCase.execute()
    }

    // MARK: - Private

    private func saveCurrentSettings() {
        saveSettingsUseCase.execute(settings: settings)
    }
}
