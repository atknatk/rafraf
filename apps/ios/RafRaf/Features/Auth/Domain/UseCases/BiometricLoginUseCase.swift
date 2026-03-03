import Foundation

/// Biyometrik dogrulama ile giris is mantigi.
/// Face ID / Touch ID dogrulamasi basariliysa Keychain'den token okunur.
struct BiometricLoginUseCase: Sendable {
    private let biometricManager: BiometricAuthManager
    private let authManager: AuthManager

    init(
        biometricManager: BiometricAuthManager,
        authManager: AuthManager
    ) {
        self.biometricManager = biometricManager
        self.authManager = authManager
    }

    /// Biyometrik dogrulama ile giris yapar.
    /// - Throws: BiometricError veya diger hatalar.
    @MainActor
    func execute() async throws {
        guard biometricManager.isBiometricAvailable else {
            throw BiometricError.notAvailable
        }

        guard authManager.isBiometricEnabled else {
            throw BiometricError.notAvailable
        }

        // Biyometrik dogrulama yap
        try await biometricManager.authenticate(
            reason: String(localized: "auth.biometric.reason")
        )

        // Keychain'de token var mi kontrol et
        await authManager.checkExistingAuth()
    }
}
