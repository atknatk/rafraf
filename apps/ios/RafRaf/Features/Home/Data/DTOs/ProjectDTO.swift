import Foundation

/// Proje API response DTO.
/// Sunucudan gelen JSON verisini temsil eder.
struct ProjectDTO: Codable, Sendable {
    let id: String
    let name: String
    let description: String
    let createdAt: String
    let updatedAt: String
    let status: String
}
