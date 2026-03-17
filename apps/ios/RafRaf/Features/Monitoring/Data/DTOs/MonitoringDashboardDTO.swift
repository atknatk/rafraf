import Foundation

/// GET /api/v1/monitoring/dashboard response DTO.
struct MonitoringDashboardDTO: Codable, Sendable {
    let timestamp: String
    let system: SystemHealthDTO
    let agents: AgentOverviewDTO
    let usage: UsageOverviewDTO
    let pulse: PulseSummaryDTO?
}

struct SystemHealthDTO: Codable, Sendable {
    let status: String
    let uptimeSeconds: Double
    let startedAt: String
    let cpuPercent: Double
    let memoryPercent: Double
    let memoryUsedMb: Double
    let components: [ComponentHealthDTO]
}

struct ComponentHealthDTO: Codable, Sendable {
    let name: String
    let status: String
    let latencyMs: Double?
    let detail: String?
}

struct AgentOverviewDTO: Codable, Sendable {
    let total: Int
    let online: Int
    let offline: Int
    let busy: Int
    let agents: [AgentBriefDTO]
}

struct AgentBriefDTO: Codable, Sendable {
    let hostId: String
    let status: String
    let cpuPercent: Double
    let memoryPercent: Double
    let activeTasks: Int
    let uptimeSeconds: Int
}

struct UsageOverviewDTO: Codable, Sendable {
    let subscriptionType: String
    let usagePercent: Double
    let dailyMessageLimit: Int
    let totalMessagesToday: Int
    let isRateLimited: Bool
    let warningThresholdReached: Bool
    let limitExceeded: Bool
}

struct PulseSummaryDTO: Codable, Sendable {
    let summaryText: String
    let totalMessages: Int
    let totalCostUsd: Double?
    let reportDate: String
    let risks: [String]
    let suggestions: [String]
}
