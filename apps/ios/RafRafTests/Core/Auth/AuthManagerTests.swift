import Foundation
import Testing
@testable import RafRaf

/// AuthManager testleri.
@Suite("AuthManager Tests")
struct AuthManagerTests {

    @Test("Baslangic durumu unknown olmali")
    @MainActor
    func initialStateIsUnknown() {
        let manager = AuthManager(keychain: KeychainHelper(service: "com.rafraf.test.\(UUID().uuidString)"))
        #expect(manager.authState == .unknown)
    }

    @Test("Token kaydettikten sonra authenticated olmali")
    @MainActor
    func saveTokensSetsAuthenticated() {
        let manager = AuthManager(keychain: KeychainHelper(service: "com.rafraf.test.\(UUID().uuidString)"))

        manager.saveTokens(
            accessToken: "access-123",
            refreshToken: "refresh-456",
            expiresIn: 900
        )

        #expect(manager.authState == .authenticated)
        #expect(manager.currentAccessToken == "access-123")
        #expect(manager.currentRefreshToken == "refresh-456")
    }

    @Test("clearTokens unauthenticated yapmalI")
    @MainActor
    func clearTokensSetsUnauthenticated() {
        let manager = AuthManager(keychain: KeychainHelper(service: "com.rafraf.test.\(UUID().uuidString)"))

        manager.saveTokens(
            accessToken: "access",
            refreshToken: "refresh",
            expiresIn: 900
        )
        manager.clearTokens()

        #expect(manager.authState == .unauthenticated)
        #expect(manager.currentAccessToken == nil)
        #expect(manager.currentRefreshToken == nil)
    }

    @Test("checkExistingAuth token yoksa unauthenticated olmali")
    @MainActor
    func checkExistingAuthNoToken() async {
        let manager = AuthManager(keychain: KeychainHelper(service: "com.rafraf.test.\(UUID().uuidString)"))

        await manager.checkExistingAuth()

        #expect(manager.authState == .unauthenticated)
    }

    @Test("checkExistingAuth gecerli token varsa authenticated olmali")
    @MainActor
    func checkExistingAuthWithValidToken() async {
        let keychainService = "com.rafraf.test.\(UUID().uuidString)"
        let keychain = KeychainHelper(service: keychainService)

        // Token'lari kaydet
        try! keychain.saveString("access-token", for: "auth_access_token")
        try! keychain.saveString("refresh-token", for: "auth_refresh_token")
        let futureDate = Date().addingTimeInterval(900)
        let expiresAtString = ISO8601DateFormatter().string(from: futureDate)
        try! keychain.saveString(expiresAtString, for: "auth_token_expires_at")

        let manager = AuthManager(keychain: keychain)
        await manager.checkExistingAuth()

        #expect(manager.authState == .authenticated)
    }

    @Test("Biyometrik tercih kaydetme ve okuma")
    @MainActor
    func biometricPreference() {
        let manager = AuthManager(keychain: KeychainHelper(service: "com.rafraf.test.\(UUID().uuidString)"))

        #expect(manager.isBiometricEnabled == false)

        manager.setBiometricEnabled(true)
        #expect(manager.isBiometricEnabled == true)

        manager.setBiometricEnabled(false)
        #expect(manager.isBiometricEnabled == false)
    }
}
