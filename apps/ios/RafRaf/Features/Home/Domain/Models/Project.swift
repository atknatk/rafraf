import Foundation

/// Proje domain modeli.
/// Kullanicinin olusturup yonettigi projeleri temsil eder.
struct Project: Identifiable, Sendable, Equatable {
    let id: String
    let name: String
    let description: String?
    let status: ProjectStatus
    let repositoryURL: String?
    /// Claude -p'nin çalıştırılacağı lokal dizin yolu.
    let localPath: String?
    let techStack: [String]
    let lastActivityAt: Date?
    let lastActivitySummary: String?
    let createdAt: Date
    let updatedAt: Date

    init(
        id: String = UUID().uuidString,
        name: String,
        description: String? = nil,
        status: ProjectStatus = .active,
        repositoryURL: String? = nil,
        localPath: String? = nil,
        techStack: [String] = [],
        lastActivityAt: Date? = nil,
        lastActivitySummary: String? = nil,
        createdAt: Date = Date(),
        updatedAt: Date = Date()
    ) {
        self.id = id
        self.name = name
        self.description = description
        self.status = status
        self.repositoryURL = repositoryURL
        self.localPath = localPath
        self.techStack = techStack
        self.lastActivityAt = lastActivityAt
        self.lastActivitySummary = lastActivitySummary
        self.createdAt = createdAt
        self.updatedAt = updatedAt
    }
}

/// Proje durumlari.
enum ProjectStatus: String, Sendable, Equatable, CaseIterable {
    case active
    case pending
    case completed
    case archived
}
