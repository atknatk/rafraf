import Foundation

/// Agent projeleri use case.
final class GetAgentProjectsUseCase: Sendable {
    private let repository: AgentRepositoryProtocol

    init(repository: AgentRepositoryProtocol) {
        self.repository = repository
    }

    func execute(agentId: String) async throws -> [AgentProject] {
        try await repository.getAgentProjects(agentId: agentId)
    }
}
