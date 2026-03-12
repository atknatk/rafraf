import Foundation

/// Proaktif bildirim tipi kategorileri.
/// Backend'deki ProactiveNotificationType enum degerlerine karsilik gelir.
enum ProactiveNotificationType: String, Sendable, CaseIterable, Codable, Equatable {
    case taskComplete = "task_complete"
    case issueDetected = "issue_detected"
    case suggestion = "suggestion"
    case reminder = "reminder"
    case ciFailure = "ci_failure"
    case prMerged = "pr_merged"
    case securityAlert = "security_alert"

    /// Kullaniciya gosterilecek lokalize baslik.
    var localizedTitle: String {
        switch self {
        case .taskComplete:
            return String(localized: "proactive.type.taskComplete")
        case .issueDetected:
            return String(localized: "proactive.type.issueDetected")
        case .suggestion:
            return String(localized: "proactive.type.suggestion")
        case .reminder:
            return String(localized: "proactive.type.reminder")
        case .ciFailure:
            return String(localized: "proactive.type.ciFailure")
        case .prMerged:
            return String(localized: "proactive.type.prMerged")
        case .securityAlert:
            return String(localized: "proactive.type.securityAlert")
        }
    }

    /// Kategori ikonu (SF Symbol).
    var iconName: String {
        switch self {
        case .taskComplete: return "checkmark.circle.fill"
        case .issueDetected: return "exclamationmark.triangle.fill"
        case .suggestion: return "lightbulb.fill"
        case .reminder: return "bell.fill"
        case .ciFailure: return "xmark.octagon.fill"
        case .prMerged: return "arrow.triangle.merge"
        case .securityAlert: return "shield.exclamationmark.fill"
        }
    }
}
