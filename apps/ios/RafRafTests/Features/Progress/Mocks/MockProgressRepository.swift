import Foundation
@testable import RafRaf

/// Test icin mock progress repository.
final class MockProgressRepository: ProgressRepositoryProtocol, @unchecked Sendable {
    var currentProgressResult: Result<ProgressState?, Error> = .success(nil)
    var updateProgressResult: Result<Void, Error> = .success(())
    var clearProgressResult: Result<Void, Error> = .success(())

    var currentProgressCallCount = 0
    var updateProgressCallCount = 0
    var clearProgressCallCount = 0
    var lastSessionId: String?
    var lastUpdatedState: ProgressState?

    func currentProgress(sessionId: String) async throws -> ProgressState? {
        currentProgressCallCount += 1
        lastSessionId = sessionId
        return try currentProgressResult.get()
    }

    func updateProgress(sessionId: String, state: ProgressState) async throws {
        updateProgressCallCount += 1
        lastSessionId = sessionId
        lastUpdatedState = state
        try updateProgressResult.get()
    }

    func clearProgress(sessionId: String) async throws {
        clearProgressCallCount += 1
        lastSessionId = sessionId
        try clearProgressResult.get()
    }
}
