import Foundation

/// Agent projesi aktiflik durumu degistirme use case.
final class SetProjectActiveUseCase: Sendable {
    private let repository: AgentRepositoryProtocol

    init(repository: AgentRepositoryProtocol) {
        self.repository = repository
    }

    func execute(agentId: String, projectId: String, isActive: Bool) async throws -> AgentProject {
        try await repository.setProjectActive(agentId: agentId, projectId: projectId, isActive: isActive)
    }
}
