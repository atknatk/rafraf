import Foundation

/// Host Agent domain modeli.
struct Agent: Identifiable, Sendable, Equatable {
    var id: String { hostId }
    let hostId: String
    let status: AgentStatus
    let capabilities: [AgentCapability]
    let osInfo: String?
    let uptimeSeconds: Int?
    let activeTasks: Int?
    let lastHeartbeatAt: Date?
    let resources: AgentResourceInfo?
}

/// Agent baglanti durumu.
enum AgentStatus: String, Sendable, CaseIterable {
    case online
    case offline
    case busy
}

/// Agent yetenekleri.
enum AgentCapability: String, Sendable, CaseIterable {
    case docker
    case playwright
    case maestroIos = "maestro_ios"
    case maestroAndroid = "maestro_android"
    case shell
    case xcodeBuild = "xcode_build"
    case androidBuild = "android_build"
    case git
    case python
    case nodejs
}

/// Agent sistem kaynak bilgileri.
struct AgentResourceInfo: Sendable, Equatable {
    let cpuUsagePercent: Double
    let memoryUsagePercent: Double
    let diskUsagePercent: Double
    let diskFreeGb: Double
}

/// Agent listesi sonuc modeli.
struct AgentListResult: Sendable, Equatable {
    let agents: [Agent]
    let total: Int
    let onlineCount: Int
}
