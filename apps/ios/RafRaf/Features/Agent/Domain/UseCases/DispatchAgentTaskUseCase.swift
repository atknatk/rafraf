import Foundation

/// Agent'a yeni gorev gondermek icin use case.
struct DispatchAgentTaskUseCase: Sendable {
    private let repository: AgentRepositoryProtocol

    init(repository: AgentRepositoryProtocol) {
        self.repository = repository
    }

    func execute(agentId: String, runner: String, action: String, params: [String: String]) async throws {
        try await repository.dispatchTask(
            agentId: agentId,
            runner: runner,
            action: action,
            params: params
        )
    }
}
