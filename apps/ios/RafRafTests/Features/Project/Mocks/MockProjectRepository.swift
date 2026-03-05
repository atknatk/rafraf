import Foundation
@testable import RafRaf

/// Test icin mock proje repository.
final class MockProjectRepository: ProjectStatusRepositoryProtocol, @unchecked Sendable {
    // MARK: - Call Tracking

    var getProjectsCallCount = 0
    var getProjectsLastStatus: ProjectStatus?
    var getProjectsLastPage: Int?
    var getProjectsLastPageSize: Int?

    var getProjectCallCount = 0
    var getProjectLastId: String?

    // MARK: - Return Values

    var getProjectsResult: Result<ProjectListResult, Error> = .success(
        ProjectListResult(projects: [], total: 0, page: 1, pageSize: 20)
    )

    var getProjectResult: Result<Project, Error> = .success(
        Project(name: "Mock Project")
    )

    // MARK: - Protocol

    func getProjects(
        status: ProjectStatus?,
        agentId: String? = nil,
        page: Int,
        pageSize: Int
    ) async throws -> ProjectListResult {
        getProjectsCallCount += 1
        getProjectsLastStatus = status
        getProjectsLastPage = page
        getProjectsLastPageSize = pageSize
        return try getProjectsResult.get()
    }

    func getProject(id projectId: String) async throws -> Project {
        getProjectCallCount += 1
        getProjectLastId = projectId
        return try getProjectResult.get()
    }

    func updateProjectStatus(projectId: String, status: ProjectStatus) async throws -> Project {
        Project(id: projectId, name: "Mock Project", status: status)
    }

    func deduplicateProjects() async throws -> Int { 0 }
}

/// Test icin stub agent repository (proje testleri icin).
final class StubAgentRepository: AgentRepositoryProtocol, @unchecked Sendable {
    func getAgents(status: AgentStatus?) async throws -> AgentListResult {
        AgentListResult(agents: [], total: 0, onlineCount: 0)
    }
    func getSubscriptionUsage() async throws -> SubscriptionUsage {
        SubscriptionUsage(subscriptionType: "max", usedSessions: 0, maxSessions: nil, resetAt: nil, isUnlimited: true)
    }
    func refreshSubscriptionUsage() async throws -> SubscriptionUsage {
        try await getSubscriptionUsage()
    }
    func getAgentProjects(agentId: String) async throws -> [AgentProject] { [] }
    func setProjectActive(agentId: String, projectId: String, isActive: Bool) async throws -> AgentProject {
        AgentProject(agentId: agentId, projectId: projectId, projectName: "", isActive: isActive, repositoryUrl: nil, localPath: nil, techStack: [])
    }
    func getClaudeProcesses(agentId: String) async throws -> [ClaudeProcess] { [] }
}
