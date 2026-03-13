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

    enum CodingKeys: String, CodingKey {
        case id, type, priority, title, body, source, metadata
        case sourceEvent = "source_event"
        case deepLink = "deep_link"
        case isRead = "is_read"
        case readAt = "read_at"
        case createdAt = "created_at"
    }
}

/// Proaktif bildirim listesi response DTO.
struct ProactiveNotificationListDTO: Codable, Sendable {
    let notifications: [ProactiveNotificationDTO]
    let total: Int
    let page: Int
    let pageSize: Int

    enum CodingKeys: String, CodingKey {
        case notifications, total, page
        case pageSize = "page_size"
    }
}

/// Okunmamis bildirim sayisi response DTO.
struct UnreadCountDTO: Codable, Sendable {
    let count: Int
}

/// Tumunu okundu isaretle response DTO.
struct MarkAllReadDTO: Codable, Sendable {
    let markedCount: Int

    enum CodingKeys: String, CodingKey {
        case markedCount = "marked_count"
    }
}
