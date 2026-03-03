import Foundation
import Testing
@testable import RafRaf

/// RegisterDeviceTokenUseCase testleri.
@Suite("RegisterDeviceTokenUseCase Tests")
struct RegisterDeviceTokenUseCaseTests {

    @Test("Token basariyla kaydedilmeli")
    func successfulRegistration() async throws {
        let mockRepo = MockNotificationRepository()
        let expectedId = UUID()
        let expectedDate = Date()
        mockRepo.registerResult = DeviceTokenRegistration(
            id: expectedId,
            registeredAt: expectedDate
        )

        let useCase = RegisterDeviceTokenUseCase(repository: mockRepo)
        let result = try await useCase.execute(token: "test-apns-token")

        #expect(result.id == expectedId)
        #expect(result.registeredAt == expectedDate)
        #expect(mockRepo.registerCallCount == 1)
        #expect(mockRepo.lastRegisteredToken == "test-apns-token")
    }

    @Test("Repository hatasi firlatilmali")
    func repositoryError() async {
        let mockRepo = MockNotificationRepository()
        mockRepo.registerError = NetworkError.serverError("Server error")

        let useCase = RegisterDeviceTokenUseCase(repository: mockRepo)

        do {
            _ = try await useCase.execute(token: "test-token")
            Issue.record("Hata bekleniyor ama basarili oldu")
        } catch {
            #expect(mockRepo.registerCallCount == 1)
        }
    }
}
