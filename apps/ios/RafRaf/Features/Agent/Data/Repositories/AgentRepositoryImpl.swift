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
}
