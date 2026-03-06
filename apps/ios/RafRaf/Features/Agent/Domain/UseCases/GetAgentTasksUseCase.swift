import Foundation

/// Agent gorev gecmisini getiren use case.
struct GetAgentTasksUseCase: Sendable {
    private let repository: AgentRepositoryProtocol

    init(repository: AgentRepositoryProtocol) {
        self.repository = repository
    }

    func execute(agentId: String, limit: Int = 50) async throws -> AgentTaskListResult {
        try await repository.getAgentTasks(agentId: agentId, limit: limit)
    }
}
