import Foundation

/// Proje DTO -> Domain donusturucu.
enum ProjectMapper {
    /// DTO'yu domain modeline donusturur.
    static func toDomain(_ dto: ProjectDTO) -> Project {
        let dateFormatter = ISO8601DateFormatter()

        return Project(
            id: dto.id,
            name: dto.name,
            description: dto.description,
            status: ProjectStatus(rawValue: dto.status) ?? .active,
            createdAt: dateFormatter.date(from: dto.createdAt) ?? Date(),
            updatedAt: dateFormatter.date(from: dto.updatedAt) ?? Date()
        )
    }

    /// DTO listesini domain modeline donusturur.
    static func toDomain(_ dtos: [ProjectDTO]) -> [Project] {
        dtos.map { toDomain($0) }
    }
}
