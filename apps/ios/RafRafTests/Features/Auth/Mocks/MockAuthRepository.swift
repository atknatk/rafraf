import Foundation
@testable import RafRaf

/// Test icin mock auth repository.
final class MockAuthRepository: AuthRepositoryProtocol, @unchecked Sendable {
    var loginResult: Result<AuthToken, Error> = .success(
        AuthToken(
            accessToken: "test-access-token",
            refreshToken: "test-refresh-token",
            tokenType: "bearer",
            expiresIn: 900,
            expiresAt: Date().addingTimeInterval(900)
        )
    )

    var refreshResult: Result<AuthToken, Error> = .success(
        AuthToken(
            accessToken: "new-access-token",
            refreshToken: "new-refresh-token",
            tokenType: "bearer",
            expiresIn: 900,
            expiresAt: Date().addingTimeInterval(900)
        )
    )

    var loginCallCount = 0
    var refreshCallCount = 0
    var lastLoginEmail: String?
    var lastLoginPassword: String?
    var lastRefreshToken: String?

    func login(email: String, password: String) async throws -> AuthToken {
        loginCallCount += 1
        lastLoginEmail = email
        lastLoginPassword = password
        return try loginResult.get()
    }

    func refreshToken(refreshToken: String) async throws -> AuthToken {
        refreshCallCount += 1
        lastRefreshToken = refreshToken
        return try refreshResult.get()
    }
}
