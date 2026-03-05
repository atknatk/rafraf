import Foundation
import os

/// Proje repository implementasyonu.
/// REST API uzerinden proje verilerini getirir.
final class ProjectRepositoryImpl: ProjectStatusRepositoryProtocol, @unchecked Sendable {
    private let networkClient: NetworkClient
    private let logger = AppLogger.logger(for: "ProjectRepository")

    init(networkClient: NetworkClient) {
        self.networkClient = networkClient
    }

    func getProjects(
        status: ProjectStatus?,
        agentId: String? = nil,
        page: Int,
        pageSize: Int
    ) async throws -> ProjectListResult {
        var queryItems: [URLQueryItem] = [
            URLQueryItem(name: "page", value: String(page)),
            URLQueryItem(name: "page_size", value: String(pageSize))
        ]

        if let status {
            queryItems.append(URLQueryItem(name: "status", value: status.rawValue))
        }
        if let agentId {
            queryItems.append(URLQueryItem(name: "agent_id", value: agentId))
        }

        let dto: ProjectListResponseDTO = try await networkClient.get(
            path: "/projects",
            queryItems: queryItems
        )

        logger.info("Proje listesi alindi: \(dto.projects.count) proje, toplam: \(dto.total)")

        return ProjectStatusMapper.toDomain(from: dto)
    }

    func getProject(id projectId: String) async throws -> Project {
        let dto: ProjectDetailDTO = try await networkClient.get(
            path: "/projects/\(projectId)"
        )

        logger.info("Proje detayi alindi: \(dto.name)")

        return ProjectStatusMapper.toDomain(from: dto)
    }

    func updateProjectStatus(projectId: String, status: ProjectStatus) async throws -> Project {
        let body = UpdateProjectStatusRequestDTO(status: status.rawValue)
        let dto: ProjectDetailDTO = try await networkClient.patch(
            path: "/projects/\(projectId)/status",
            body: body
        )

        logger.info("Proje durumu guncellendi: \(dto.name) -> \(status.rawValue)")

        return ProjectStatusMapper.toDomain(from: dto)
    }

    func deduplicateProjects() async throws -> Int {
        struct Response: Decodable { let deletedCount: Int }
        let response: Response = try await networkClient.post(
            path: "/projects/deduplicate",
            body: [String: String]()
        )
        logger.info("Deduplicate tamamlandi: \(response.deletedCount) silindi")
        return response.deletedCount
    }
}
