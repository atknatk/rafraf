import Foundation
import os

/// Proje repository implementasyonu.
/// REST API uzerinden proje verilerini getirir.
final class ProjectRepositoryImpl: ProjectRepositoryProtocol, @unchecked Sendable {
    private let networkClient: NetworkClient
    private let logger = AppLogger.logger(for: "ProjectRepository")

    init(networkClient: NetworkClient) {
        self.networkClient = networkClient
    }

    func getProjects(
        status: ProjectStatus?,
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

        let dto: ProjectListResponseDTO = try await networkClient.get(
            path: "/api/v1/projects",
            queryItems: queryItems
        )

        logger.info("Proje listesi alindi: \(dto.projects.count) proje, toplam: \(dto.total)")

        return ProjectMapper.toDomain(from: dto)
    }

    func getProject(id projectId: String) async throws -> Project {
        let dto: ProjectDetailDTO = try await networkClient.get(
            path: "/api/v1/projects/\(projectId)"
        )

        logger.info("Proje detayi alindi: \(dto.name)")

        return ProjectMapper.toDomain(from: dto)
    }
}
