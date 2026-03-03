import Foundation
import os

/// NetworkClient isteklerine JWT token enjekte eden interceptor.
/// Her istege Authorization header ekler, 401 yaniti gelirse bildirim gonderir.
final class AuthInterceptor: Sendable {
    private let keychain: KeychainHelper
    private let logger = Logger(
        subsystem: "com.rafraf",
        category: "AuthInterceptor"
    )

    init(keychain: KeychainHelper = KeychainHelper()) {
        self.keychain = keychain
    }

    /// Istege Authorization header'i ekler.
    /// - Parameter request: Orijinal URLRequest.
    /// - Returns: Token eklenmis URLRequest.
    func intercept(_ request: URLRequest) -> URLRequest {
        var modifiedRequest = request
        if let token = keychain.readString(for: "auth_access_token") {
            modifiedRequest.setValue(
                "Bearer \(token)",
                forHTTPHeaderField: "Authorization"
            )
            logger.debug("Authorization header eklendi")
        }
        return modifiedRequest
    }

    /// Mevcut bir access token var mi kontrol eder.
    var hasAccessToken: Bool {
        keychain.readString(for: "auth_access_token") != nil
    }
}
