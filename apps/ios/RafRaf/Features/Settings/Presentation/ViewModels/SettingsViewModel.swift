import Foundation
import os

/// Ayarlar ViewModel.
/// Settings ekraninin durumunu ve islemlerini yonetir.
@Observable
@MainActor
final class SettingsViewModel {
    // MARK: - State

    var displayName: String = "RafRaf User"
    var email: String = "user@rafraf.app"
    var errorMessage: String?

    // MARK: - Computed

    var appVersion: String {
        let version = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "1.0"
        let build = Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? "1"
        return "\(version) (\(build))"
    }

    // MARK: - Private

    private let logger = AppLogger.logger(for: "Settings")

    // MARK: - Init

    init() {
        logger.info("SettingsViewModel baslatildi")
    }

    // MARK: - Actions

    /// Cikis yapar.
    func logout() async {
        logger.info("Cikis yapiliyor")
        // Placeholder - auth implementasyonunda doldurulacak
    }
}
