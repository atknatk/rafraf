import Foundation

/// Agent listesi use case.
/// Agent'lari filtre ile getirir.
final class GetAgentsUseCase: Sendable {
    private let repository: AgentRepositoryProtocol

    init(repository: AgentRepositoryProtocol) {
        self.repository = repository
    }

    /// Agent listesini getirir.
    /// - Parameter status: Opsiyonel durum filtresi
    /// - Returns: Agent listesi sonucu
    func execute(status: AgentStatus? = nil) async throws -> AgentListResult {
        try await repository.getAgents(status: status)
    }
}
