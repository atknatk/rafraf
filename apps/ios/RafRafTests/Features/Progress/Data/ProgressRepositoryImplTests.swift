import Foundation
import Testing
@testable import RafRaf

/// ProgressRepositoryImpl testleri.
@Suite("ProgressRepositoryImpl Tests")
struct ProgressRepositoryImplTests {

    // MARK: - Helpers

    private func makeSUT() -> ProgressRepositoryImpl {
        ProgressRepositoryImpl()
    }

    // MARK: - Current Progress

    @Test("currentProgress bos repository icin nil donmeli")
    func currentProgressEmpty() async throws {
        let sut = makeSUT()

        let result = try await sut.currentProgress(sessionId: "session-1")

        #expect(result == nil)
    }

    @Test("currentProgress guncellenmis state'i donmeli")
    func currentProgressAfterUpdate() async throws {
        let sut = makeSUT()
        let state = ProgressTestFactory.createState(taskDescription: "Gorev 1")

        try await sut.updateProgress(sessionId: "session-1", state: state)
        let result = try await sut.currentProgress(sessionId: "session-1")

        #expect(result != nil)
        #expect(result?.taskDescription == "Gorev 1")
    }

    @Test("currentProgress farkli session'lar icin izole olmali")
    func currentProgressDifferentSessions() async throws {
        let sut = makeSUT()
        let state1 = ProgressTestFactory.createState(taskDescription: "Gorev A")
        let state2 = ProgressTestFactory.createState(taskDescription: "Gorev B")

        try await sut.updateProgress(sessionId: "session-a", state: state1)
        try await sut.updateProgress(sessionId: "session-b", state: state2)

        let resultA = try await sut.currentProgress(sessionId: "session-a")
        let resultB = try await sut.currentProgress(sessionId: "session-b")

        #expect(resultA?.taskDescription == "Gorev A")
        #expect(resultB?.taskDescription == "Gorev B")
    }

    // MARK: - Update Progress

    @Test("updateProgress mevcut state'i degistirmeli")
    func updateProgressOverwrite() async throws {
        let sut = makeSUT()
        let state1 = ProgressTestFactory.createState(percentage: 30)
        let state2 = ProgressTestFactory.createState(percentage: 80)

        try await sut.updateProgress(sessionId: "session-1", state: state1)
        try await sut.updateProgress(sessionId: "session-1", state: state2)
        let result = try await sut.currentProgress(sessionId: "session-1")

        #expect(result?.percentage == 80)
    }

    // MARK: - Clear Progress

    @Test("clearProgress session'in progress'ini temizlemeli")
    func clearProgress() async throws {
        let sut = makeSUT()
        let state = ProgressTestFactory.createState()

        try await sut.updateProgress(sessionId: "session-1", state: state)
        try await sut.clearProgress(sessionId: "session-1")
        let result = try await sut.currentProgress(sessionId: "session-1")

        #expect(result == nil)
    }

    @Test("clearProgress diger session'lari etkilememeli")
    func clearProgressIsolation() async throws {
        let sut = makeSUT()
        let state1 = ProgressTestFactory.createState(taskDescription: "A")
        let state2 = ProgressTestFactory.createState(taskDescription: "B")

        try await sut.updateProgress(sessionId: "session-1", state: state1)
        try await sut.updateProgress(sessionId: "session-2", state: state2)
        try await sut.clearProgress(sessionId: "session-1")

        let result1 = try await sut.currentProgress(sessionId: "session-1")
        let result2 = try await sut.currentProgress(sessionId: "session-2")

        #expect(result1 == nil)
        #expect(result2 != nil)
        #expect(result2?.taskDescription == "B")
    }

    @Test("clearProgress olmayan session icin hata atmamalI")
    func clearProgressNonexistent() async throws {
        let sut = makeSUT()

        // Hata atmamalI
        try await sut.clearProgress(sessionId: "nonexistent")
    }
}
