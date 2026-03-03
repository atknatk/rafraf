import Foundation
import os

/// Bildirim ayarlari ViewModel.
/// Push bildirim izin durumu, device token kaydi ve
/// bildirim kategorisi tercihlerini yonetir.
@Observable
@MainActor
final class NotificationSettingsViewModel {

    // MARK: - State

    /// Bildirim izni durumu.
    var permissionStatus: PermissionStatus = .unknown

    /// Bildirim tercihleri.
    var preferences: NotificationPreferences = NotificationPreferences(
        taskCompleteEnabled: true,
        approvalNeededEnabled: true,
        errorEnabled: true,
        infoEnabled: true
    )

    /// Yuklenme durumu.
    var isLoading: Bool = false

    /// Hata mesaji.
    var errorMessage: String?

    /// Device token kayit durumu.
    var isTokenRegistered: Bool = false

    // MARK: - Types

    enum PermissionStatus: Sendable {
        case unknown
        case authorized
        case denied
        case provisional
    }

    // MARK: - Private

    private let registerDeviceTokenUseCase: RegisterDeviceTokenUseCase
    private let notificationManager: PushNotificationManager
    private let repository: NotificationRepositoryProtocol
    private let logger = AppLogger.logger(for: "NotificationSettings")

    // MARK: - Init

    init(
        registerDeviceTokenUseCase: RegisterDeviceTokenUseCase,
        notificationManager: PushNotificationManager,
        repository: NotificationRepositoryProtocol
    ) {
        self.registerDeviceTokenUseCase = registerDeviceTokenUseCase
        self.notificationManager = notificationManager
        self.repository = repository
        logger.info("NotificationSettingsViewModel baslatildi")
    }

    // MARK: - Actions

    /// Bildirim izni ister ve ayarlari yukler.
    func onAppear() async {
        notificationManager.refreshAuthorizationStatus()
        // Kisa bekleme - status guncellenmesi icin
        try? await Task.sleep(for: .milliseconds(100))
        updatePermissionStatus()
        await loadSettings()
    }

    /// Bildirim izni ister.
    func requestPermission() async {
        await notificationManager.requestAuthorization()
        updatePermissionStatus()

        // Izin verildiyse token kaydi yap
        if permissionStatus == .authorized,
           let token = notificationManager.deviceToken {
            await registerToken(token)
        }
    }

    /// Device token'i backend'e kaydeder.
    /// - Parameter token: APNs device token string'i.
    func registerToken(_ token: String) async {
        do {
            _ = try await registerDeviceTokenUseCase.execute(token: token)
            isTokenRegistered = true
            logger.info("Device token kaydedildi")
        } catch {
            logger.error("Device token kayit hatasi: \(error.localizedDescription)")
            errorMessage = String(localized: "notification.error.tokenRegistration")
        }
    }

    /// Bildirim kategorisi tercihini gunceller.
    /// - Parameters:
    ///   - category: Bildirim kategorisi.
    ///   - enabled: Aktif mi.
    func updateCategory(_ category: NotificationCategory, enabled: Bool) async {
        var update = NotificationPreferencesUpdate()
        switch category {
        case .taskComplete:
            update.taskCompleteEnabled = enabled
        case .approvalNeeded:
            update.approvalNeededEnabled = enabled
        case .error:
            update.errorEnabled = enabled
        case .info:
            update.infoEnabled = enabled
        }

        do {
            preferences = try await repository.updateNotificationSettings(update)
            logger.info("Bildirim tercihi guncellendi: \(category.rawValue) = \(enabled)")
        } catch {
            logger.error("Bildirim tercihi guncelleme hatasi: \(error.localizedDescription)")
            errorMessage = String(localized: "notification.error.updateSettings")
        }
    }

    /// Belirli bir kategori aktif mi.
    /// - Parameter category: Sorgulanacak kategori.
    /// - Returns: Aktiflik durumu.
    func isCategoryEnabled(_ category: NotificationCategory) -> Bool {
        switch category {
        case .taskComplete: return preferences.taskCompleteEnabled
        case .approvalNeeded: return preferences.approvalNeededEnabled
        case .error: return preferences.errorEnabled
        case .info: return preferences.infoEnabled
        }
    }

    // MARK: - Private

    private func loadSettings() async {
        isLoading = true
        do {
            preferences = try await repository.getNotificationSettings()
            logger.info("Bildirim ayarlari yuklendi")
        } catch {
            logger.error("Bildirim ayarlari yukleme hatasi: \(error.localizedDescription)")
            errorMessage = String(localized: "notification.error.loadSettings")
        }
        isLoading = false
    }

    private func updatePermissionStatus() {
        switch notificationManager.authorizationStatus {
        case .authorized:
            permissionStatus = .authorized
        case .denied:
            permissionStatus = .denied
        case .provisional:
            permissionStatus = .provisional
        default:
            permissionStatus = .unknown
        }
    }
}
