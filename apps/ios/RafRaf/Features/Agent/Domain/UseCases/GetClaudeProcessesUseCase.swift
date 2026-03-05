import Foundation

/// Agent Claude process listesi use case.
final class GetClaudeProcessesUseCase: Sendable {
    private let repository: AgentRepositoryProtocol

    init(repository: AgentRepositoryProtocol) {
        self.repository = repository
    }

    func execute(agentId: String) async throws -> [ClaudeProcess] {
        try await repository.getClaudeProcesses(agentId: agentId)
    }
}
