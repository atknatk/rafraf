import Foundation

/// Agent DTO -> Domain model donusturucusu.
enum AgentMapper {
    /// AgentSummaryDTO'yu Agent domain modeline donusturur.
    static func toDomain(from dto: AgentSummaryDTO) -> Agent {
        Agent(
            hostId: dto.hostId,
            status: AgentStatus(rawValue: dto.status) ?? .offline,
            capabilities: dto.capabilities.compactMap { AgentCapability(rawValue: $0) },
            osInfo: dto.osInfo,
            uptimeSeconds: dto.uptimeSeconds,
            activeTasks: dto.activeTasks,
            lastHeartbeatAt: parseDate(dto.lastHeartbeatAt),
            resources: dto.resources.map { toDomain(from: $0) }
        )
    }

    /// ResourceInfoDTO'yu AgentResourceInfo domain modeline donusturur.
    static func toDomain(from dto: ResourceInfoDTO) -> AgentResourceInfo {
        AgentResourceInfo(
            cpuUsagePercent: dto.cpuUsagePercent,
            memoryUsagePercent: dto.memoryUsagePercent,
            diskUsagePercent: dto.diskUsagePercent,
            diskFreeGb: dto.diskFreeGb
        )
    }

    /// AgentListResponseDTO'yu AgentListResult domain modeline donusturur.
    static func toDomain(from dto: AgentListResponseDTO) -> AgentListResult {
        AgentListResult(
            agents: dto.agents.map { toDomain(from: $0) },
            total: dto.total,
            onlineCount: dto.onlineCount
        )
    }

    // MARK: - Private Helpers

    private static func parseDate(_ dateString: String?) -> Date? {
        guard let dateString else { return nil }
        return ISO8601DateFormatter().date(from: dateString)
    }
}
