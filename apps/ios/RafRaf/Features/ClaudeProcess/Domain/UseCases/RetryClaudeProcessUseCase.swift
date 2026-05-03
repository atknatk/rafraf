import Foundation

/// V1.x SLIM — Banner Retry butonu use case'i.
///
/// Kullanici tap → use case → repository.requestRetry → bridge re-spawn.
/// Use case ince bir wrapper; aydinlatici DI noktasi olarak korunur.
public struct RetryClaudeProcessUseCase: Sendable {
    private let repository: ClaudeProcessRepository

    public init(repository: ClaudeProcessRepository) {
        self.repository = repository
    }

    /// Spec §4.7 — `command.claude.process.retry` envelope'ini bridge'e yollar.
    public func execute(sessionId: String) async throws {
        try await repository.requestRetry(sessionId: sessionId)
    }
}
