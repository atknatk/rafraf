import Foundation
import os

/// Ayarlar ViewModel.
/// Settings ekraninin durumunu ve islemlerini yonetir.
/// Ses, bildirim, gorunum ve hesap ayarlarini yonetir.
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

    /// TTS hizi gosterge metni.
    var ttsSpeedText: String {
        String(format: "%.1fx", settings.ttsSpeed)
    }

    // MARK: - Private

    private let loadSettingsUseCase: LoadSettingsUseCase
    private let saveSettingsUseCase: SaveSettingsUseCase
    private let loadProfileUseCase: LoadProfileUseCase
    private let updateProfileUseCase: UpdateProfileUseCase
    private let logger = AppLogger.logger(for: "Settings")

    // MARK: - Init

    init(
        loadSettingsUseCase: LoadSettingsUseCase,
        saveSettingsUseCase: SaveSettingsUseCase,
        loadProfileUseCase: LoadProfileUseCase,
        updateProfileUseCase: UpdateProfileUseCase
    ) {
        self.loadSettingsUseCase = loadSettingsUseCase
        self.saveSettingsUseCase = saveSettingsUseCase
        self.loadProfileUseCase = loadProfileUseCase
        self.updateProfileUseCase = updateProfileUseCase
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

    /// TTS hizini gunceller.
    /// - Parameter speed: Yeni hiz degeri (0.5 - 2.0).
    func updateTTSSpeed(_ speed: Double) {
        let clampedSpeed = min(max(speed, 0.5), 2.0)
        settings.ttsSpeed = clampedSpeed
        saveCurrentSettings()
        logger.info("TTS hizi guncellendi: \(clampedSpeed)")
    }

    /// TTS otomatik oynatma durumunu degistirir.
    /// - Parameter enabled: Aktif mi.
    func updateTTSAutoPlay(_ enabled: Bool) {
        settings.ttsAutoPlay = enabled
        saveCurrentSettings()
        logger.info("TTS auto-play guncellendi: \(enabled)")
    }

    /// TTS dilini degistirir.
    /// - Parameter language: Yeni dil secimi.
    func updateTTSLanguage(_ language: TTSLanguage) {
        settings.ttsLanguage = language
        saveCurrentSettings()
        logger.info("TTS dili guncellendi: \(language.rawValue)")
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

    /// Cikis onay dialogunu gosterir.
    func showLogoutConfirmation() {
        isShowingLogoutConfirmation = true
    }

    /// Cikis yapar.
    func logout() async {
        logger.info("Cikis yapiliyor")
        // AuthManager uzerinden logout islemi yapilir.
        // Bu ViewModel sadece Settings scope'unda calisir.
    }

    // MARK: - Private

    private func saveCurrentSettings() {
        saveSettingsUseCase.execute(settings: settings)
    }
}
