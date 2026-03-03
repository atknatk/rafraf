import Foundation

/// Token yenileme is mantigi.
/// Refresh token ile yeni access/refresh token pair alir.
struct RefreshTokenUseCase: Sendable {
    private let repository: AuthRepositoryProtocol

    init(repository: AuthRepositoryProtocol) {
        self.repository = repository
    }

    /// Token yenileme islemini gerceklestirir.
    /// - Parameter refreshToken: Mevcut refresh token.
    /// - Returns: Yeni JWT token bilgileri.
    func execute(refreshToken: String) async throws -> AuthToken {
        try await repository.refreshToken(refreshToken: refreshToken)
    }
}
