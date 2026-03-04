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
