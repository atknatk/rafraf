import Foundation

/// MonitoringDashboardDTO -> Domain model donusturucusu.
enum MonitoringMapper {
    static func toDomain(from dto: MonitoringDashboardDTO) -> MonitoringDashboard {
        MonitoringDashboard(
            timestamp: parseDate(dto.timestamp) ?? Date(),
            system: toDomain(from: dto.system),
            agents: toDomain(from: dto.agents),
            usage: toDomain(from: dto.usage),
            pulse: dto.pulse.map { toDomain(from: $0) }
        )
    }

    private static func toDomain(from dto: SystemHealthDTO) -> SystemHealth {
        SystemHealth(
            status: SystemStatus(rawValue: dto.status) ?? .unhealthy,
            uptimeSeconds: dto.uptimeSeconds,
            startedAt: parseDate(dto.startedAt),
            cpuPercent: dto.cpuPercent,
            memoryPercent: dto.memoryPercent,
            memoryUsedMb: dto.memoryUsedMb,
            components: dto.components.map { toDomain(from: $0) }
        )
    }

    private static func toDomain(from dto: ComponentHealthDTO) -> ComponentHealth {
        ComponentHealth(
            name: dto.name,
            status: dto.status,
            latencyMs: dto.latencyMs,
            detail: dto.detail
        )
    }

    private static func toDomain(from dto: AgentOverviewDTO) -> AgentFleetOverview {
        AgentFleetOverview(
            total: dto.total,
            online: dto.online,
            offline: dto.offline,
            busy: dto.busy,
            agents: dto.agents.map { toDomain(from: $0) }
        )
    }

    private static func toDomain(from dto: AgentBriefDTO) -> AgentBrief {
        AgentBrief(
            hostId: dto.hostId,
            status: dto.status,
            cpuPercent: dto.cpuPercent,
            memoryPercent: dto.memoryPercent,
            activeTasks: dto.activeTasks,
            uptimeSeconds: dto.uptimeSeconds
        )
    }

    private static func toDomain(from dto: UsageOverviewDTO) -> UsageOverview {
        UsageOverview(
            subscriptionType: dto.subscriptionType,
            usagePercent: dto.usagePercent,
            dailyMessageLimit: dto.dailyMessageLimit,
            totalMessagesToday: dto.totalMessagesToday,
            isRateLimited: dto.isRateLimited,
            warningThresholdReached: dto.warningThresholdReached,
            limitExceeded: dto.limitExceeded
        )
    }

    private static func toDomain(from dto: PulseSummaryDTO) -> PulseSummary {
        PulseSummary(
            summaryText: dto.summaryText,
            totalMessages: dto.totalMessages,
            totalCostUsd: dto.totalCostUsd,
            reportDate: dto.reportDate,
            risks: dto.risks,
            suggestions: dto.suggestions
        )
    }

    private static func parseDate(_ dateString: String?) -> Date? {
        guard let dateString else { return nil }
        return ISO8601DateFormatter().date(from: dateString)
    }
}
