import Foundation

/// V1.x SLIM — Banner stream'ini gozlemleyen use case.
///
/// `RFClaudeProcessBanner` bu stream'i SwiftUI `.task` icinde tuketir.
/// Repository nil yayinlarsa banner gizlenir.
public struct ObserveClaudeProcessBannerUseCase: Sendable {
    private let repository: ClaudeProcessRepository

    public init(repository: ClaudeProcessRepository) {
        self.repository = repository
    }

    public func execute(sessionId: String) async -> AsyncStream<ClaudeProcessBannerState?> {
        await repository.observeBanner(sessionId: sessionId)
    }
}
