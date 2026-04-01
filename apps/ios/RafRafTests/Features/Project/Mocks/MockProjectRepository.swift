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

    func createProject(
        name: String,
        description: String?,
        repositoryURL: String?,
        localPath: String?,
        techStack: [String]
    ) async throws -> String { "mock-project-id" }

    func updateProject(
        projectId: String,
        name: String?,
        description: String?,
        repositoryURL: String?,
        localPath: String?,
        techStack: [String]?
    ) async throws -> Project {
        Project(name: name ?? "Mock Project")
    }
}

/// Test icin stub agent repository (proje testleri icin).
final class StubAgentRepository: AgentRepositoryProtocol, @unchecked Sendable {
    func getAgents(status: AgentStatus?) async throws -> AgentListResult {
        AgentListResult(agents: [], total: 0, onlineCount: 0)
    }
    func getSubscriptionUsage() async throws -> SubscriptionUsage {
        SubscriptionUsage(
            subscriptionType: "max",
            email: nil,
            orgName: nil,
            todayUsage: DailyUsageStats(date: "2026-04-01", messageCount: 0, sessionCount: 0, toolCallCount: 0),
            recentDays: [],
            totalMessagesToday: 0,
            isRateLimited: false,
            rateLimitResetAt: nil,
            usagePercent: 0,
            dailyMessageLimit: 100,
            warningThresholdReached: false,
            limitExceeded: false,
            lastFetchedAt: Date()
        )
    }
    func refreshSubscriptionUsage() async throws -> SubscriptionUsage {
        try await getSubscriptionUsage()
    }
    func getAgentProjects(agentId: String) async throws -> [AgentProject] { [] }
    func setProjectActive(agentId: String, projectId: String, isActive: Bool) async throws -> AgentProject {
        AgentProject(agentId: agentId, projectId: projectId, projectName: "", isActive: isActive, repositoryUrl: nil, localPath: nil, techStack: [])
    }
    func getClaudeProcesses(agentId: String) async throws -> [ClaudeProcess] { [] }
    func getAllAgentProjects() async throws -> [AgentProject] { [] }
    func getAgentTasks(agentId: String, limit: Int) async throws -> AgentTaskListResult {
        AgentTaskListResult(tasks: [], total: 0, pendingCount: 0)
    }
    func cancelAgentTask(agentId: String, taskId: String) async throws {}
    func dispatchTask(agentId: String, runner: String, action: String, params: [String: String]) async throws {}
    func rescanProjects(agentId: String) async throws {}
    func getAgentSkipPermissions(agentId: String) async throws -> Bool { false }
    func updateAgentSettings(agentId: String, dangerouslySkipPermissions: Bool) async throws {}
}
