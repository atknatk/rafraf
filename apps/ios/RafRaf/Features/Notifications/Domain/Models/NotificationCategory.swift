import Foundation

/// Push bildirim kategorileri.
/// Backend'den gelen notification type degerlerine karsilik gelir.
enum NotificationCategory: String, Sendable, CaseIterable, Equatable {
    case taskComplete = "task_complete"
    case approvalNeeded = "approval_needed"
    case error = "error"
    case info = "info"

    /// Kullaniciya gosterilecek lokalize baslik.
    var localizedTitle: String {
        switch self {
        case .taskComplete:
            return String(localized: "notification.category.taskComplete")
        case .approvalNeeded:
            return String(localized: "notification.category.approvalNeeded")
        case .error:
            return String(localized: "notification.category.error")
        case .info:
            return String(localized: "notification.category.info")
        }
    }

    /// Kategori iconu (SF Symbol).
    var iconName: String {
        switch self {
        case .taskComplete: return "checkmark.circle.fill"
        case .approvalNeeded: return "hand.raised.fill"
        case .error: return "exclamationmark.triangle.fill"
        case .info: return "info.circle.fill"
        }
    }
}
