import Foundation

/// Bildirim oncelik seviyeleri.
enum NotificationPriority: String, Sendable, CaseIterable, Codable, Equatable, Comparable {
    case urgent = "urgent"
    case normal = "normal"
    case low = "low"

    /// Siralama icin numerik deger (urgent en yuksek).
    private var sortOrder: Int {
        switch self {
        case .urgent: return 0
        case .normal: return 1
        case .low: return 2
        }
    }

    static func < (lhs: NotificationPriority, rhs: NotificationPriority) -> Bool {
        lhs.sortOrder < rhs.sortOrder
    }

    /// Lokalize etiket.
    var localizedTitle: String {
        switch self {
        case .urgent:
            return String(localized: "proactive.priority.urgent")
        case .normal:
            return String(localized: "proactive.priority.normal")
        case .low:
            return String(localized: "proactive.priority.low")
        }
    }
}
