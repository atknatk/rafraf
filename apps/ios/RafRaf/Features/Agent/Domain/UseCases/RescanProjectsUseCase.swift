import Foundation

/// Agent proje rescan use case.
final class RescanProjectsUseCase: Sendable {
    private let repository: AgentRepositoryProtocol

    init(repository: AgentRepositoryProtocol) {
        self.repository = repository
    }

    func execute(agentId: String) async throws {
        try await repository.rescanProjects(agentId: agentId)
    }
}
