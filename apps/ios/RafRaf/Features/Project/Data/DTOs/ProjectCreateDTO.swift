import Foundation

/// POST /api/v1/projects request body DTO.
/// `shared/api-contracts/rest/v1/projects.json` kontratina uygun.
/// NetworkClient `keyEncodingStrategy = .convertToSnakeCase` kullanir.
struct ProjectCreateRequestDTO: Encodable, Sendable {
    let name: String
    let description: String?
    let repositoryUrl: String?
    let localPath: String?
    let techStack: [String]
    let source: String

    init(
        name: String,
        description: String? = nil,
        repositoryUrl: String? = nil,
        localPath: String? = nil,
        techStack: [String] = [],
        source: String = "manual"
    ) {
        self.name = name
        self.description = description
        self.repositoryUrl = repositoryUrl
        self.localPath = localPath
        self.techStack = techStack
        self.source = source
    }
}

/// PATCH /api/v1/projects/{id} request body DTO.
struct ProjectUpdateRequestDTO: Encodable, Sendable {
    let name: String?
    let description: String?
    let repositoryUrl: String?
    let localPath: String?
    let techStack: [String]?

    init(
        name: String? = nil,
        description: String? = nil,
        repositoryUrl: String? = nil,
        localPath: String? = nil,
        techStack: [String]? = nil
    ) {
        self.name = name
        self.description = description
        self.repositoryUrl = repositoryUrl
        self.localPath = localPath
        self.techStack = techStack
    }
}

/// POST /api/v1/projects response DTO.
struct ProjectCreateResponseDTO: Decodable, Sendable {
    let id: String
    let name: String
    let status: String
    let createdAt: String
}
