import Foundation
import os

/// Bos istek govdesi — body gerektiren ama icerik olmayan endpoint'ler icin.
private struct EmptyBody: Encodable, Sendable {}

/// Proaktif bildirim repository implementasyonu.
/// NetworkClient uzerinden backend API'sine erisir.
final class ProactiveNotificationRepositoryImpl: ProactiveNotificationRepositoryProtocol, @unchecked Sendable {

    private let networkClient: NetworkClient
    private let logger = Logger(
        subsystem: "com.rafraf",
        category: "ProactiveNotificationRepository"
    )

    init(networkClient: NetworkClient) {
        self.networkClient = networkClient
    }

    func getNotifications(
        page: Int,
        pageSize: Int,
        priority: NotificationPriority?,
        isRead: Bool?,
        type: ProactiveNotificationType?
    ) async throws -> ProactiveNotificationListResult {
        logger.info("Proaktif bildirimler getiriliyor: page=\(page)")
        var queryItems = [
            URLQueryItem(name: "page", value: String(page)),
            URLQueryItem(name: "page_size", value: String(pageSize))
        ]
        if let priority {
            queryItems.append(URLQueryItem(name: "priority", value: priority.rawValue))
        }
        if let isRead {
            queryItems.append(URLQueryItem(name: "is_read", value: String(isRead)))
        }
        if let type {
            queryItems.append(URLQueryItem(name: "type", value: type.rawValue))
        }

        let response: ProactiveNotificationListDTO = try await networkClient.get(
            path: "/proactive-notifications",
            queryItems: queryItems
        )
        return ProactiveNotificationMapper.toDomain(response)
    }

    func markAsRead(notificationId: UUID) async throws -> ProactiveNotification {
        logger.info("Bildirim okundu isaretleniyor: \(notificationId)")
        let response: ProactiveNotificationDTO = try await networkClient.patch(
            path: "/proactive-notifications/\(notificationId)/read",
            body: EmptyBody()
        )
        return ProactiveNotificationMapper.toDomain(response)
    }

    func markAllAsRead() async throws -> Int {
        logger.info("Tum bildirimler okundu isaretleniyor")
        let response: MarkAllReadDTO = try await networkClient.post(
            path: "/proactive-notifications/read-all",
            body: EmptyBody()
        )
        return response.markedCount
    }

    func deleteNotification(notificationId: UUID) async throws {
        logger.info("Bildirim siliniyor: \(notificationId)")
        try await networkClient.delete(
            path: "/proactive-notifications/\(notificationId)"
        )
    }

    func getUnreadCount() async throws -> Int {
        logger.info("Okunmamis bildirim sayisi getiriliyor")
        let response: UnreadCountDTO = try await networkClient.get(
            path: "/proactive-notifications/unread-count"
        )
        return response.count
    }
}
