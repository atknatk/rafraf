import Foundation

/// Agent ayarlarini guncelleme use case.
final class UpdateAgentSettingsUseCase: Sendable {
    private let repository: AgentRepositoryProtocol

    init(repository: AgentRepositoryProtocol) {
        self.repository = repository
    }

    func execute(agentId: String, dangerouslySkipPermissions: Bool) async throws {
        try await repository.updateAgentSettings(
            agentId: agentId,
            dangerouslySkipPermissions: dangerouslySkipPermissions
        )
    }
}

/// Agent dangerouslySkipPermissions degerini getirme use case.
final class GetAgentSkipPermissionsUseCase: Sendable {
    private let repository: AgentRepositoryProtocol

    init(repository: AgentRepositoryProtocol) {
        self.repository = repository
    }

    func execute(agentId: String) async throws -> Bool {
        try await repository.getAgentSkipPermissions(agentId: agentId)
    }
}
