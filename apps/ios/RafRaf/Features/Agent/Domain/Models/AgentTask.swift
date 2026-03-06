import Foundation

/// Agent gorev durum enum.
enum AgentTaskStatus: String, Codable, Sendable {
    case pending
    case running
    case completed
    case failed
    case cancelled
    case timeout

    var isTerminal: Bool {
        switch self {
        case .completed, .failed, .cancelled, .timeout: return true
        case .pending, .running: return false
        }
    }

    var isCancellable: Bool {
        switch self {
        case .pending, .running: return true
        case .completed, .failed, .cancelled, .timeout: return false
        }
    }
}

/// Agent gorevi domain modeli.
struct AgentTask: Identifiable, Sendable {
    let id: String        // task_id
    let hostId: String
    let runner: String
    let action: String
    let status: AgentTaskStatus
    let projectId: String?
    let createdAt: Date
    let startedAt: Date?
    let completedAt: Date?
    let durationMs: Int?
    let error: String?

    var durationText: String? {
        guard let ms = durationMs else { return nil }
        if ms < 1000 { return "\(ms)ms" }
        return String(format: "%.1fs", Double(ms) / 1000)
    }
}

/// Agent gorev listesi sonucu.
struct AgentTaskListResult: Sendable {
    let tasks: [AgentTask]
    let total: Int
    let pendingCount: Int
}
