import Foundation

/// Agent gorevini iptal eden use case.
struct CancelAgentTaskUseCase: Sendable {
    private let repository: AgentRepositoryProtocol

    init(repository: AgentRepositoryProtocol) {
        self.repository = repository
    }

    func execute(agentId: String, taskId: String) async throws {
        try await repository.cancelAgentTask(agentId: agentId, taskId: taskId)
    }
}
