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
}
