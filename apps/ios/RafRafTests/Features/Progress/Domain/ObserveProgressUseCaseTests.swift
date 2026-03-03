import Foundation
import Testing
@testable import RafRaf

/// ObserveProgressUseCase testleri.
@Suite("ObserveProgressUseCase Tests")
struct ObserveProgressUseCaseTests {

    // MARK: - Helpers

    private func makeSUT(
        repository: MockProgressRepository = MockProgressRepository()
    ) -> (ObserveProgressUseCase, MockProgressRepository) {
        let useCase = ObserveProgressUseCase(repository: repository)
        return (useCase, repository)
    }

    // MARK: - Execute (Current Progress)

    @Test("execute mevcut progress olmadigi durumda nil donmeli")
    func executeNoProgress() async throws {
        let (sut, _) = makeSUT()

        let result = try await sut.execute(sessionId: "session-1")

        #expect(result == nil)
    }

    @Test("execute mevcut progress varsa state donmeli")
    func executeWithProgress() async throws {
        let repo = MockProgressRepository()
        let state = ProgressTestFactory.createState(taskDescription: "Active gorev")
        repo.currentProgressResult = .success(state)
        let (sut, _) = makeSUT(repository: repo)

        let result = try await sut.execute(sessionId: "session-1")

        #expect(result != nil)
        #expect(result?.taskDescription == "Active gorev")
        #expect(repo.currentProgressCallCount == 1)
        #expect(repo.lastSessionId == "session-1")
    }

    @Test("execute repository hatasi attiginda hata iletmeli")
    func executeError() async {
        let repo = MockProgressRepository()
        repo.currentProgressResult = .failure(ProgressTestError.repositoryError)
        let (sut, _) = makeSUT(repository: repo)

        do {
            _ = try await sut.execute(sessionId: "session-1")
            #expect(Bool(false), "Hata bekleniyor")
        } catch {
            #expect(error is ProgressTestError)
        }
    }

    // MARK: - Update

    @Test("update repository'ye state gondermeli")
    func updateProgress() async throws {
        let (sut, repo) = makeSUT()
        let state = ProgressTestFactory.createState(percentage: 75)

        try await sut.update(sessionId: "session-2", state: state)

        #expect(repo.updateProgressCallCount == 1)
        #expect(repo.lastSessionId == "session-2")
        #expect(repo.lastUpdatedState?.percentage == 75)
    }

    @Test("update repository hatasi attiginda hata iletmeli")
    func updateError() async {
        let repo = MockProgressRepository()
        repo.updateProgressResult = .failure(ProgressTestError.repositoryError)
        let (sut, _) = makeSUT(repository: repo)
        let state = ProgressTestFactory.createState()

        do {
            try await sut.update(sessionId: "session-1", state: state)
            #expect(Bool(false), "Hata bekleniyor")
        } catch {
            #expect(error is ProgressTestError)
        }
    }

    // MARK: - Clear

    @Test("clear repository'den progress temizlemeli")
    func clearProgress() async throws {
        let (sut, repo) = makeSUT()

        try await sut.clear(sessionId: "session-3")

        #expect(repo.clearProgressCallCount == 1)
        #expect(repo.lastSessionId == "session-3")
    }

    @Test("clear repository hatasi attiginda hata iletmeli")
    func clearError() async {
        let repo = MockProgressRepository()
        repo.clearProgressResult = .failure(ProgressTestError.repositoryError)
        let (sut, _) = makeSUT(repository: repo)

        do {
            try await sut.clear(sessionId: "session-1")
            #expect(Bool(false), "Hata bekleniyor")
        } catch {
            #expect(error is ProgressTestError)
        }
    }
}

// MARK: - Test Errors

enum ProgressTestError: Error {
    case repositoryError
}
