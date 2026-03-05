import Foundation
import os

/// Agent repository implementasyonu.
/// REST API uzerinden agent verilerini getirir.
final class AgentRepositoryImpl: AgentRepositoryProtocol, @unchecked Sendable {
    private let networkClient: NetworkClient
    private let logger = AppLogger.logger(for: "AgentRepository")

    init(networkClient: NetworkClient) {
        self.networkClient = networkClient
    }

    func getAgents(status: AgentStatus?) async throws -> AgentListResult {
        var queryItems: [URLQueryItem] = []

        if let status {
            queryItems.append(URLQueryItem(name: "status", value: status.rawValue))
        }

        let dto: AgentListResponseDTO = try await networkClient.get(
            path: "/agents",
            queryItems: queryItems.isEmpty ? nil : queryItems
        )

        logger.info("Agent listesi alindi: \(dto.agents.count) agent, online: \(dto.onlineCount)")

        return AgentMapper.toDomain(from: dto)
    }

    func getSubscriptionUsage() async throws -> SubscriptionUsage {
        let dto: SubscriptionUsageDTO = try await networkClient.get(
            path: "/subscription/usage"
        )
        logger.info("Subscription kullanim alindi: \(dto.subscriptionType)")
        return AgentMapper.toDomain(from: dto)
    }

    func refreshSubscriptionUsage() async throws -> SubscriptionUsage {
        let dto: SubscriptionUsageDTO = try await networkClient.post(
            path: "/subscription/usage/refresh",
            body: [String: String]()
        )
        logger.info("Subscription kullanim yenilendi: \(dto.subscriptionType)")
        return AgentMapper.toDomain(from: dto)
    }

    func getAgentProjects(agentId: String) async throws -> [AgentProject] {
        let dto: AgentProjectsResponseDTO = try await networkClient.get(
            path: "/agents/\(agentId)/projects"
        )
        logger.info("Agent projeleri alindi: \(dto.projects.count) proje")
        return AgentMapper.toDomain(from: dto)
    }

    func setProjectActive(agentId: String, projectId: String, isActive: Bool) async throws -> AgentProject {
        struct Body: Encodable { let is_active: Bool }
        let dto: AgentProjectSummaryDTO = try await networkClient.patch(
            path: "/agents/\(agentId)/projects/\(projectId)",
            body: Body(is_active: isActive)
        )
        logger.info("Proje aktiflik degistirildi: \(projectId) -> \(isActive)")
        return AgentProject(
            agentId: agentId,
            projectId: dto.projectId,
            projectName: dto.projectName,
            isActive: dto.isActive,
            repositoryUrl: dto.repositoryUrl,
            localPath: dto.localPath,
            techStack: dto.techStack
        )
    }

    func getClaudeProcesses(agentId: String) async throws -> [ClaudeProcess] {
        let dto: AgentProcessesResponseDTO = try await networkClient.get(
            path: "/agents/\(agentId)/processes"
        )
        logger.info("Claude process'ler alindi: \(dto.processes.count) process")
        return AgentMapper.toDomain(from: dto)
    }

    func getAllAgentProjects() async throws -> [AgentProject] {
        let dtos: [AgentProjectsResponseDTO] = try await networkClient.get(
            path: "/agents/all-linked-projects"
        )
        logger.info("Tum agent projeleri alindi: \(dtos.count) agent")
        return dtos.flatMap { AgentMapper.toDomain(from: $0) }
    }

    func getAgentTasks(agentId: String, limit: Int) async throws -> AgentTaskListResult {
        let dto: AgentTaskListResponseDTO = try await networkClient.get(
            path: "/agents/\(agentId)/tasks",
            queryItems: [URLQueryItem(name: "limit", value: "\(limit)")]
        )
        logger.info("Agent gorevleri alindi: \(dto.tasks.count) gorev")
        return AgentMapper.toDomain(from: dto)
    }

    func cancelAgentTask(agentId: String, taskId: String) async throws {
        try await networkClient.delete(path: "/agents/\(agentId)/tasks/\(taskId)")
        logger.info("Gorev iptal edildi: \(taskId)")
    }

    func dispatchTask(agentId: String, runner: String, action: String, params: [String: String]) async throws {
        struct Body: Encodable {
            let runner: String
            let action: String
            let params: [String: String]
        }
        let _: AgentTaskListResponseDTO = try await networkClient.post(
            path: "/agents/\(agentId)/tasks",
            body: Body(runner: runner, action: action, params: params)
        )
        logger.info("Gorev gonderildi: \(runner)/\(action) -> \(agentId)")
    }
}
