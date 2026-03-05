import Foundation

/// Proje DTO -> Domain model donusturucusu.
enum ProjectStatusMapper {
    /// ProjectSummaryDTO'yu Project domain modeline donusturur.
    static func toDomain(from dto: ProjectSummaryDTO) -> Project {
        Project(
            id: dto.id,
            name: dto.name,
            status: ProjectStatus(rawValue: dto.status) ?? .active,
            techStack: dto.techStack,
            lastActivityAt: parseDate(dto.lastActivityAt),
            lastActivitySummary: dto.lastActivitySummary
        )
    }

    /// ProjectDetailDTO'yu Project domain modeline donusturur.
    static func toDomain(from dto: ProjectDetailDTO) -> Project {
        Project(
            id: dto.id,
            name: dto.name,
            description: dto.description,
            status: ProjectStatus(rawValue: dto.status) ?? .active,
            repositoryURL: dto.repositoryUrl,
            localPath: dto.localPath,
            techStack: dto.techStack,
            lastActivityAt: parseDate(dto.lastActivityAt),
            lastActivitySummary: dto.lastActivitySummary,
            createdAt: parseDate(dto.createdAt) ?? Date(),
            updatedAt: parseDate(dto.updatedAt) ?? Date()
        )
    }

    /// ProjectListResponseDTO'yu ProjectListResult domain modeline donusturur.
    static func toDomain(from dto: ProjectListResponseDTO) -> ProjectListResult {
        ProjectListResult(
            projects: dto.projects.map { toDomain(from: $0) },
            total: dto.total,
            page: dto.page,
            pageSize: dto.pageSize
        )
    }

    // MARK: - Private Helpers

    private static func parseDate(_ dateString: String?) -> Date? {
        guard let dateString else { return nil }
        return ISO8601DateFormatter().date(from: dateString)
    }
}
