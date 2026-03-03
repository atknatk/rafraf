import Foundation

/// Logout is mantigi.
/// AuthManager uzerinden token'lari temizler.
struct LogoutUseCase: Sendable {
    private let authManager: AuthManager

    init(authManager: AuthManager) {
        self.authManager = authManager
    }

    /// Logout islemini gerceklestirir.
    /// Tum token'lari Keychain'den temizler.
    @MainActor
    func execute() {
        authManager.clearTokens()
    }
}
