import Foundation

/// Auth repository protokolu.
/// Domain layer'da tanimlanir, Data layer'da implemente edilir.
protocol AuthRepositoryProtocol: Sendable {
    /// Email ve sifre ile giris yapar.
    /// - Parameters:
    ///   - email: Kullanici e-posta adresi.
    ///   - password: Kullanici sifresi.
    /// - Returns: JWT token bilgileri.
    func login(email: String, password: String) async throws -> AuthToken

    /// Refresh token ile yeni token pair alir.
    /// - Parameter refreshToken: Mevcut refresh token.
    /// - Returns: Yeni JWT token bilgileri.
    func refreshToken(refreshToken: String) async throws -> AuthToken
}
