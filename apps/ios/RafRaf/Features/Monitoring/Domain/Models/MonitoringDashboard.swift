import Foundation

/// Birlesik monitoring dashboard verisi.
struct MonitoringDashboard: Sendable, Equatable {
    let timestamp: Date
    let system: SystemHealth
    let agents: AgentFleetOverview
    let usage: UsageOverview
    let pulse: PulseSummary?
}

/// Backend sistem sagligi.
struct SystemHealth: Sendable, Equatable {
    let status: SystemStatus
    let uptimeSeconds: Double
    let startedAt: Date?
    let cpuPercent: Double
    let memoryPercent: Double
    let memoryUsedMb: Double
    let components: [ComponentHealth]
}

enum SystemStatus: String, Sendable {
    case healthy
    case degraded
    case unhealthy
}

/// Tek bir component'in sagligi.
struct ComponentHealth: Sendable, Equatable, Identifiable {
    var id: String { name }
    let name: String
    let status: String
    let latencyMs: Double?
    let detail: String?
}

/// Agent filosu ozeti.
struct AgentFleetOverview: Sendable, Equatable {
    let total: Int
    let online: Int
    let offline: Int
    let busy: Int
    let agents: [AgentBrief]
}

/// Dashboard icin minimal agent bilgisi.
struct AgentBrief: Sendable, Equatable, Identifiable {
    var id: String { hostId }
    let hostId: String
    let status: String
    let cpuPercent: Double
    let memoryPercent: Double
    let activeTasks: Int
    let uptimeSeconds: Int
}

/// Subscription kullanim ozeti.
struct UsageOverview: Sendable, Equatable {
    let subscriptionType: String
    let usagePercent: Double
    let dailyMessageLimit: Int
    let totalMessagesToday: Int
    let isRateLimited: Bool
    let warningThresholdReached: Bool
    let limitExceeded: Bool
}

/// Pulse rapor ozeti.
struct PulseSummary: Sendable, Equatable {
    let summaryText: String
    let totalMessages: Int
    let totalCostUsd: Double?
    let reportDate: String
    let risks: [String]
    let suggestions: [String]
}
