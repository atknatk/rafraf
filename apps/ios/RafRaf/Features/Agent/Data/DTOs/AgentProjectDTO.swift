import Foundation

/// Agent-proje listesi API yaniti DTO.
struct AgentProjectsResponseDTO: Codable, Sendable {
    let agentId: String
    let projects: [AgentProjectSummaryDTO]
    let total: Int
}

/// Tek proje ozeti DTO.
struct AgentProjectSummaryDTO: Codable, Sendable {
    let projectId: String
    let projectName: String
    let isActive: Bool
    let repositoryUrl: String?
    let localPath: String?
    let techStack: [String]

    enum CodingKeys: String, CodingKey {
        case projectId = "project_id"
        case projectName = "project_name"
        case isActive = "is_active"
        case repositoryUrl = "repository_url"
        case localPath = "local_path"
        case techStack = "tech_stack"
    }
}

/// Claude process listesi API yaniti DTO.
struct AgentProcessesResponseDTO: Codable, Sendable {
    let agentId: String
    let processes: [ClaudeProcessDTO]
    let total: Int

    enum CodingKeys: String, CodingKey {
        case agentId = "agent_id"
        case processes
        case total
    }
}

/// Tek claude process DTO.
struct ClaudeProcessDTO: Codable, Sendable {
    let pid: Int
    let cpuPercent: Double
    let memoryMb: Double
    let startedAt: String?
    let cmdline: String?

    enum CodingKeys: String, CodingKey {
        case pid
        case cpuPercent = "cpu_percent"
        case memoryMb = "memory_mb"
        case startedAt = "started_at"
        case cmdline
    }
}

/// AgentProjectsResponseDTO icindeki agentId de snake_case olabilir.
extension AgentProjectsResponseDTO {
    enum CodingKeys: String, CodingKey {
        case agentId = "agent_id"
        case projects
        case total
    }
}
