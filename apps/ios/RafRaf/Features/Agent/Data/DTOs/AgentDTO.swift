import Foundation

/// Agent ozet API response DTO.
/// Backend `GET /api/v1/agents` kontratina uygun.
/// NetworkClient `keyDecodingStrategy = .convertFromSnakeCase` kullanir.
struct AgentSummaryDTO: Codable, Sendable {
    let hostId: String
    let status: String
    let capabilities: [String]
    let lastHeartbeatAt: String?
    let osInfo: String?
    let uptimeSeconds: Int?
    let activeTasks: Int?
    let resources: ResourceInfoDTO?
}

/// Sistem kaynak bilgileri DTO.
struct ResourceInfoDTO: Codable, Sendable {
    let cpuUsagePercent: Double
    let memoryUsagePercent: Double
    let diskUsagePercent: Double
    let diskFreeGb: Double
}

/// Agent liste response DTO.
struct AgentListResponseDTO: Codable, Sendable {
    let agents: [AgentSummaryDTO]
    let total: Int
    let onlineCount: Int
}

/// Agent gorev ozet DTO.
struct AgentTaskSummaryDTO: Codable, Sendable {
    let taskId: String
    let hostId: String
    let runner: String
    let action: String
    let status: String
    let projectId: String?
    let createdAt: String
    let startedAt: String?
    let completedAt: String?
    let durationMs: Int?
    let error: String?
}

/// Agent gorev listesi response DTO.
struct AgentTaskListResponseDTO: Codable, Sendable {
    let tasks: [AgentTaskSummaryDTO]
    let total: Int
    let pendingCount: Int
}

/// Agent detay response DTO.
/// Backend `GET /api/v1/agents/{host_id}` kontratina uygun.
struct AgentDetailResponseDTO: Codable, Sendable {
    let hostId: String
    let status: String
    let capabilities: [String]
    let dangerouslySkipPermissions: Bool
}

/// Agent ayar guncelleme request DTO.
/// Backend `PATCH /api/v1/agents/{host_id}/settings` kontratina uygun.
struct AgentSettingsRequestDTO: Encodable, Sendable {
    let dangerouslySkipPermissions: Bool

    enum CodingKeys: String, CodingKey {
        case dangerouslySkipPermissions = "dangerously_skip_permissions"
    }
}
