import Foundation

/// Subscription kullanim bilgilerini yenileyen use case.
final class RefreshSubscriptionUsageUseCase: Sendable {
    private let repository: AgentRepositoryProtocol

    init(repository: AgentRepositoryProtocol) {
        self.repository = repository
    }

    func execute() async throws -> SubscriptionUsage {
        try await repository.refreshSubscriptionUsage()
    }
}
