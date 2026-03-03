import Foundation
import Testing
@testable import RafRaf

/// AuthInterceptor testleri.
@Suite("AuthInterceptor Tests")
struct AuthInterceptorTests {

    /// Keychain erisimi mevcut mu kontrol eder.
    private func isKeychainAccessible(keychain: KeychainHelper) -> Bool {
        do {
            let probe = "probe_\(UUID().uuidString)"
            try keychain.saveString("test", for: probe)
            try keychain.delete(for: probe)
            return true
        } catch {
            return false
        }
    }

    @Test("Token varsa Authorization header eklenmeli")
    func interceptAddsAuthHeader() throws {
        let keychainService = "com.rafraf.test.\(UUID().uuidString)"
        let keychain = KeychainHelper(service: keychainService)

        guard isKeychainAccessible(keychain: keychain) else { return }

        try keychain.saveString("my-access-token", for: "auth_access_token")

        let interceptor = AuthInterceptor(keychain: keychain)
        let request = URLRequest(url: URL(string: "https://example.com/api")!)

        let modified = interceptor.intercept(request)

        #expect(modified.value(forHTTPHeaderField: "Authorization") == "Bearer my-access-token")
    }

    @Test("Token yoksa Authorization header eklenmemeli")
    func interceptNoTokenNoHeader() {
        let keychain = KeychainHelper(service: "com.rafraf.test.\(UUID().uuidString)")
        let interceptor = AuthInterceptor(keychain: keychain)
        let request = URLRequest(url: URL(string: "https://example.com/api")!)

        let modified = interceptor.intercept(request)

        #expect(modified.value(forHTTPHeaderField: "Authorization") == nil)
    }

    @Test("hasAccessToken token varsa true donmeli")
    func hasAccessTokenTrue() throws {
        let keychainService = "com.rafraf.test.\(UUID().uuidString)"
        let keychain = KeychainHelper(service: keychainService)

        guard isKeychainAccessible(keychain: keychain) else { return }

        try keychain.saveString("token", for: "auth_access_token")

        let interceptor = AuthInterceptor(keychain: keychain)
        #expect(interceptor.hasAccessToken == true)
    }

    @Test("hasAccessToken token yoksa false donmeli")
    func hasAccessTokenFalse() {
        let keychain = KeychainHelper(service: "com.rafraf.test.\(UUID().uuidString)")
        let interceptor = AuthInterceptor(keychain: keychain)
        #expect(interceptor.hasAccessToken == false)
    }
}
