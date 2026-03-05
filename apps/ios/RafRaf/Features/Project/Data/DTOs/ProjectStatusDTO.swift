import Foundation

/// Proje ozet API response DTO.
/// `shared/api-contracts/rest/v1/projects.json` kontratina uygun.
/// NetworkClient `keyDecodingStrategy = .convertFromSnakeCase` kullanir.
struct ProjectSummaryDTO: Codable, Sendable {
    let id: String
    let name: String
    let status: String
    let localPath: String?
    let lastActivityAt: String?
    let lastActivitySummary: String?
    let techStack: [String]
}

/// Proje liste response DTO.
struct ProjectListResponseDTO: Codable, Sendable {
    let projects: [ProjectSummaryDTO]
    let total: Int
    let page: Int
    let pageSize: Int
}

/// Proje durumu guncelleme request DTO.
struct UpdateProjectStatusRequestDTO: Codable, Sendable {
    let status: String
}

/// Proje detay response DTO.
struct ProjectDetailDTO: Codable, Sendable {
    let id: String
    let name: String
    let description: String?
    let status: String
    let repositoryUrl: String?
    let localPath: String?
    let techStack: [String]
    let lastActivityAt: String?
    let lastActivitySummary: String?
    let createdAt: String
    let updatedAt: String
}
