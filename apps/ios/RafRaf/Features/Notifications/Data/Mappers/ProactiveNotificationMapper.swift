import Foundation

/// ProactiveNotification DTO -> Domain model donusumleri.
enum ProactiveNotificationMapper {
    /// ProactiveNotificationDTO -> ProactiveNotification
    static func toDomain(
        _ dto: ProactiveNotificationDTO
    ) -> ProactiveNotification {
        ProactiveNotification(
            id: dto.id,
            type: ProactiveNotificationType(rawValue: dto.type) ?? .issueDetected,
            priority: NotificationPriority(rawValue: dto.priority) ?? .normal,
            title: dto.title,
            body: dto.body,
            source: dto.source,
            sourceEvent: dto.sourceEvent,
            deepLink: dto.deepLink,
            metadata: dto.metadata ?? [:],
            isRead: dto.isRead,
            readAt: dto.readAt,
            createdAt: dto.createdAt
        )
    }

    /// ProactiveNotificationListDTO -> ProactiveNotificationListResult
    static func toDomain(
        _ dto: ProactiveNotificationListDTO
    ) -> ProactiveNotificationListResult {
        ProactiveNotificationListResult(
            notifications: dto.notifications.map { toDomain($0) },
            total: dto.total,
            page: dto.page,
            pageSize: dto.pageSize
        )
    }
}
