import Foundation
import os

/// Kimlik dogrulama durumu.
enum AuthState: Sendable, Equatable {
    /// Uygulama acilisinda henuz kontrol edilmedi.
    case unknown
    /// Kullanici basariyla dogrulandi.
    case authenticated
    /// Kullanici dogrulanmadi veya oturumu sonlandi.
    case unauthenticated
}

/// Keychain anahtarlari.
private enum AuthKeychainKey {
    static let accessToken = "auth_access_token"
    static let refreshToken = "auth_refresh_token"
    static let tokenExpiresAt = "auth_token_expires_at"
    static let biometricEnabled = "auth_biometric_enabled"
}

/// JWT token yonetimi, auto-refresh ve auth state yonetimi.
/// Tum uygulama genelinde auth durumunu @Observable ile yayar.
@Observable
@MainActor
final class AuthManager {
    // MARK: - State

    var authState: AuthState = .unknown

    // MARK: - Private

    private let keychain: KeychainHelper
    private let logger = AppLogger.logger(for: "AuthManager")
    private var refreshTask: Task<Void, Never>?

    // MARK: - Init

    init(keychain: KeychainHelper = KeychainHelper()) {
        self.keychain = keychain
        logger.info("AuthManager baslatildi")
    }

    // MARK: - Public API

    /// Uygulama acilisinda Keychain'den token kontrol eder.
    /// Token varsa ve gecerliyse authenticated, degilse unauthenticated state'e gecer.
    func checkExistingAuth() async {
        logger.info("Mevcut auth durumu kontrol ediliyor")

        guard let accessToken = keychain.readString(for: AuthKeychainKey.accessToken),
              !accessToken.isEmpty else {
            logger.info("Keychain'de token bulunamadi")
            authState = .unauthenticated
            return
        }

        // Token expire kontrolu
        if let expiresAtString = keychain.readString(for: AuthKeychainKey.tokenExpiresAt),
           let expiresAt = ISO8601DateFormatter().date(from: expiresAtString),
           expiresAt > Date() {
            logger.info("Gecerli token bulundu, authenticated")
            authState = .authenticated
            scheduleTokenRefresh(expiresAt: expiresAt)
        } else if keychain.readString(for: AuthKeychainKey.refreshToken) != nil {
            // Access token expired ama refresh token var, refresh denenecek
            logger.info("Access token expired, refresh denenecek")
            authState = .authenticated
        } else {
            logger.info("Token expired ve refresh token yok")
            authState = .unauthenticated
        }
    }

    /// Token bilgilerini Keychain'e kaydeder ve authenticated state'e gecer.
    /// - Parameters:
    ///   - accessToken: JWT access token.
    ///   - refreshToken: JWT refresh token.
    ///   - expiresIn: Token gecerlilik suresi (saniye).
    func saveTokens(
        accessToken: String,
        refreshToken: String,
        expiresIn: Int
    ) {
        do {
            try keychain.saveString(accessToken, for: AuthKeychainKey.accessToken)
            try keychain.saveString(refreshToken, for: AuthKeychainKey.refreshToken)

            let expiresAt = Date().addingTimeInterval(TimeInterval(expiresIn))
            let expiresAtString = ISO8601DateFormatter().string(from: expiresAt)
            try keychain.saveString(expiresAtString, for: AuthKeychainKey.tokenExpiresAt)

            authState = .authenticated
            scheduleTokenRefresh(expiresAt: expiresAt)
            logger.info("Token'lar Keychain'e kaydedildi")
        } catch {
            logger.error("Token kaydetme hatasi: \(error.localizedDescription)")
        }
    }

    /// Mevcut access token'i dondurur.
    /// - Returns: Access token veya nil.
    var currentAccessToken: String? {
        keychain.readString(for: AuthKeychainKey.accessToken)
    }

    /// Mevcut refresh token'i dondurur.
    /// - Returns: Refresh token veya nil.
    var currentRefreshToken: String? {
        keychain.readString(for: AuthKeychainKey.refreshToken)
    }

    /// Tum token'lari temizler ve unauthenticated state'e gecer.
    func clearTokens() {
        refreshTask?.cancel()
        refreshTask = nil

        do {
            try keychain.deleteAll()
            authState = .unauthenticated
            logger.info("Tum token'lar temizlendi, logout yapildi")
        } catch {
            logger.error("Token temizleme hatasi: \(error.localizedDescription)")
            authState = .unauthenticated
        }
    }

    /// Biyometrik dogrulama tercihini kaydeder.
    /// - Parameter enabled: Biyometrik aktif mi.
    func setBiometricEnabled(_ enabled: Bool) {
        do {
            try keychain.saveString(enabled ? "true" : "false", for: AuthKeychainKey.biometricEnabled)
            logger.info("Biyometrik tercih guncellendi: \(enabled)")
        } catch {
            logger.error("Biyometrik tercih kaydetme hatasi: \(error.localizedDescription)")
        }
    }

    /// Biyometrik dogrulama tercihi.
    var isBiometricEnabled: Bool {
        keychain.readString(for: AuthKeychainKey.biometricEnabled) == "true"
    }

    // MARK: - Private

    private func scheduleTokenRefresh(expiresAt: Date) {
        refreshTask?.cancel()

        // Token suresinin dolmasina 60 saniye kala refresh schedule et
        let refreshInterval = expiresAt.timeIntervalSinceNow - 60
        guard refreshInterval > 0 else { return }

        refreshTask = Task { [weak self] in
            do {
                try await Task.sleep(for: .seconds(refreshInterval))
                guard !Task.isCancelled else { return }
                self?.logger.info("Token auto-refresh zamani geldi")
                // Auto-refresh ViewModel uzerinden tetiklenir
            } catch {
                // Task cancelled
            }
        }
    }
}
