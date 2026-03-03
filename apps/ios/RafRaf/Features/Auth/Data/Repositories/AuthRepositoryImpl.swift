import Foundation
import os

/// Auth repository implementasyonu.
/// NetworkClient uzerinden backend auth endpoint'lerini cagirir.
final class AuthRepositoryImpl: AuthRepositoryProtocol, Sendable {
    private let networkClient: NetworkClient
    private let logger = Logger(
        subsystem: "com.rafraf",
        category: "AuthRepository"
    )

    init(networkClient: NetworkClient) {
        self.networkClient = networkClient
    }

    func login(email: String, password: String) async throws -> AuthToken {
        logger.info("Login istegi gonderiliyor")
        let request = TokenRequestDTO(email: email, password: password)
        let response: TokenResponseDTO = try await networkClient.post(
            path: "/auth/token",
            body: request
        )
        logger.info("Login basarili")
        return AuthMapper.toDomain(response)
    }

    func refreshToken(refreshToken: String) async throws -> AuthToken {
        logger.info("Token yenileme istegi gonderiliyor")
        let request = RefreshRequestDTO(refreshToken: refreshToken)
        let response: TokenResponseDTO = try await networkClient.post(
            path: "/auth/refresh",
            body: request
        )
        logger.info("Token yenileme basarili")
        return AuthMapper.toDomain(response)
    }
}
