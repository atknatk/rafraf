import Foundation
import Testing
@testable import RafRaf

/// LoginUseCase testleri.
@Suite("LoginUseCase Tests")
struct LoginUseCaseTests {

    @Test("Basarili login token donmeli")
    func successfulLogin() async throws {
        let mockRepo = MockAuthRepository()
        let useCase = LoginUseCase(repository: mockRepo)

        let result = try await useCase.execute(
            email: "test@example.com",
            password: "password123"
        )

        #expect(result.accessToken == "test-access-token")
        #expect(result.refreshToken == "test-refresh-token")
        #expect(mockRepo.loginCallCount == 1)
        #expect(mockRepo.lastLoginEmail == "test@example.com")
        #expect(mockRepo.lastLoginPassword == "password123")
    }

    @Test("Basarisiz login hata firlatmali")
    func failedLoginThrows() async {
        let mockRepo = MockAuthRepository()
        mockRepo.loginResult = .failure(NetworkError.unauthorized)
        let useCase = LoginUseCase(repository: mockRepo)

        do {
            _ = try await useCase.execute(
                email: "wrong@example.com",
                password: "wrong"
            )
            Issue.record("Hata bekleniyordu")
        } catch {
            #expect(mockRepo.loginCallCount == 1)
        }
    }
}
