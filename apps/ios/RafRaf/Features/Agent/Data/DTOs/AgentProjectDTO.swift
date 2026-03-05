import Foundation

/// Agent-proje listesi API yaniti DTO.
struct AgentProjectsResponseDTO: Codable, Sendable {
    let agentId: String
    let projects: [AgentProjectSummaryDTO]
    let total: Int
}

/// Tek proje ozeti DTO.
/// convertFromSnakeCase strateji ile decode edilir — CodingKeys gereksiz.
struct AgentProjectSummaryDTO: Codable, Sendable {
    let projectId: String
    let projectName: String
    let isActive: Bool
    let repositoryUrl: String?
    let localPath: String?
    let techStack: [String]
}

/// Claude process listesi API yaniti DTO.
/// convertFromSnakeCase strateji ile decode edilir — CodingKeys gereksiz.
struct AgentProcessesResponseDTO: Codable, Sendable {
    let agentId: String
    let processes: [ClaudeProcessDTO]
    let total: Int
}

/// Tek claude process DTO.
/// convertFromSnakeCase strateji ile decode edilir — CodingKeys gereksiz.
struct ClaudeProcessDTO: Codable, Sendable {
    let pid: Int
    let cpuPercent: Double
    let memoryMb: Double
    let startedAt: String?
    let cmdline: String?
}
