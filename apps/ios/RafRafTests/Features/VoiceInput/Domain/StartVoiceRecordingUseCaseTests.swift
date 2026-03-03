import Foundation
import Testing
@testable import RafRaf

/// StartVoiceRecordingUseCase testleri.
@Suite("StartVoiceRecordingUseCase Tests")
struct StartVoiceRecordingUseCaseTests {

    @Test("execute: repository.startStreaming cagirilmali")
    func executeCallsRepository() async throws {
        let mockRepo = MockVoiceInputRepository()
        let sut = StartVoiceRecordingUseCase(repository: mockRepo)

        _ = try await sut.execute(language: .turkish)

        #expect(mockRepo.startStreamingCallCount == 1)
        #expect(mockRepo.lastLanguage == .turkish)
    }

    @Test("execute: farkli dil secimi iletilmeli")
    func executeWithEnglish() async throws {
        let mockRepo = MockVoiceInputRepository()
        let sut = StartVoiceRecordingUseCase(repository: mockRepo)

        _ = try await sut.execute(language: .english)

        #expect(mockRepo.lastLanguage == .english)
    }

    @Test("execute: repository hatasi firlatildinda use case da firlatmali")
    func executeThrowsOnRepositoryError() async {
        let mockRepo = MockVoiceInputRepository()
        mockRepo.startStreamingResult = .failure(VoiceInputRepositoryError.connectionFailed)
        let sut = StartVoiceRecordingUseCase(repository: mockRepo)

        do {
            _ = try await sut.execute(language: .turkish)
            Issue.record("Hata beklendi ama firlatilmadi")
        } catch {
            #expect(error is VoiceInputRepositoryError)
        }
    }
}

/// StopVoiceRecordingUseCase testleri.
@Suite("StopVoiceRecordingUseCase Tests")
struct StopVoiceRecordingUseCaseTests {

    @Test("execute: repository.stopStreaming cagirilmali")
    func executeCallsRepository() async {
        let mockRepo = MockVoiceInputRepository()
        let sut = StopVoiceRecordingUseCase(repository: mockRepo)

        await sut.execute()

        #expect(mockRepo.stopStreamingCallCount == 1)
    }
}
