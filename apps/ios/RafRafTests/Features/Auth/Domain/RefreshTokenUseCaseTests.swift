import Foundation
import Testing
@testable import RafRaf

/// RefreshTokenUseCase testleri.
@Suite("RefreshTokenUseCase Tests")
struct RefreshTokenUseCaseTests {

    @Test("Basarili refresh yeni token donmeli")
    func successfulRefresh() async throws {
        let mockRepo = MockAuthRepository()
        let useCase = RefreshTokenUseCase(repository: mockRepo)

        let result = try await useCase.execute(refreshToken: "old-refresh-token")

        #expect(result.accessToken == "new-access-token")
        #expect(result.refreshToken == "new-refresh-token")
        #expect(mockRepo.refreshCallCount == 1)
        #expect(mockRepo.lastRefreshToken == "old-refresh-token")
    }

    @Test("Basarisiz refresh hata firlatmali")
    func failedRefreshThrows() async {
        let mockRepo = MockAuthRepository()
        mockRepo.refreshResult = .failure(NetworkError.unauthorized)
        let useCase = RefreshTokenUseCase(repository: mockRepo)

        do {
            _ = try await useCase.execute(refreshToken: "expired-token")
            Issue.record("Hata bekleniyordu")
        } catch {
            #expect(mockRepo.refreshCallCount == 1)
        }
    }
}
