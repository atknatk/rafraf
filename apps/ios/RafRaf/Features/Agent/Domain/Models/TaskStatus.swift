import Foundation

/// Task durumlarini temsil eden enum.
/// Backend ile uyumlu raw value'lar kullanir.
enum TaskStatus: String, Codable, Sendable, CaseIterable {
    case queued
    case planning
    case implementing
    case testing
    case reviewing
    case completed
    case failed
    case cancelled

    /// Task aktif olarak calisiyorsa true doner.
    var isRunning: Bool {
        !isTerminal
    }

    /// Task terminal (son) durumda ise true doner.
    var isTerminal: Bool {
        switch self {
        case .completed, .failed, .cancelled:
            return true
        case .queued, .planning, .implementing, .testing, .reviewing:
            return false
        }
    }

    /// Kullaniciya gosterilecek lokalize edilmis isim.
    var displayName: String {
        switch self {
        case .queued:
            return String(localized: "task.status.queued")
        case .planning:
            return String(localized: "task.status.planning")
        case .implementing:
            return String(localized: "task.status.implementing")
        case .testing:
            return String(localized: "task.status.testing")
        case .reviewing:
            return String(localized: "task.status.reviewing")
        case .completed:
            return String(localized: "task.status.completed")
        case .failed:
            return String(localized: "task.status.failed")
        case .cancelled:
            return String(localized: "task.status.cancelled")
        }
    }
}
