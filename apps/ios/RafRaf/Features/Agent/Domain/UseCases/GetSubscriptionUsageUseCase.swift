import Foundation

/// Subscription kullanim bilgilerini getiren use case.
final class GetSubscriptionUsageUseCase: Sendable {
    private let repository: AgentRepositoryProtocol

    init(repository: AgentRepositoryProtocol) {
        self.repository = repository
    }

    func execute() async throws -> SubscriptionUsage {
        try await repository.getSubscriptionUsage()
    }
}
