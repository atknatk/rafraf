import Foundation

/// Proaktif bildirim response DTO.
struct ProactiveNotificationDTO: Codable, Sendable {
    let id: UUID
    let type: String
    let priority: String
    let title: String
    let body: String
    let source: String
    let sourceEvent: String?
    let deepLink: String?
    let metadata: [String: String]?
    let isRead: Bool
    let readAt: Date?
    let createdAt: Date
}

/// Proaktif bildirim listesi response DTO.
struct ProactiveNotificationListDTO: Codable, Sendable {
    let notifications: [ProactiveNotificationDTO]
    let total: Int
    let page: Int
    let pageSize: Int
}

/// Okunmamis bildirim sayisi response DTO.
struct UnreadCountDTO: Codable, Sendable {
    let count: Int
}

/// Tumunu okundu isaretle response DTO.
struct MarkAllReadDTO: Codable, Sendable {
    let markedCount: Int
}
