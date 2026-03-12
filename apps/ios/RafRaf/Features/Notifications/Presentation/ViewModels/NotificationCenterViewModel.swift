import Foundation
import os

/// Bildirim merkezi ViewModel.
/// Proaktif bildirimlerin listelenmesi, okundu isaretlenmesi ve silinmesini yonetir.
@Observable
@MainActor
final class NotificationCenterViewModel {

    // MARK: - State

    /// Bildirim listesi.
    var notifications: [ProactiveNotification] = []

    /// Toplam bildirim sayisi.
    var totalCount: Int = 0

    /// Okunmamis bildirim sayisi.
    var unreadCount: Int = 0

    /// Mevcut sayfa.
    var currentPage: Int = 1

    /// Sayfa basina bildirim sayisi.
    let pageSize: Int = 20

    /// Daha fazla bildirim var mi.
    var hasMore: Bool = false

    /// Yuklenme durumu.
    var isLoading: Bool = false

    /// Daha fazla yuklenme durumu.
    var isLoadingMore: Bool = false

    /// Hata mesaji.
    var errorMessage: String?

    /// Secili filtre.
    var selectedFilter: NotificationFilter = .all

    // MARK: - Types

    enum NotificationFilter: String, CaseIterable, Sendable {
        case all
        case unread
        case urgent

        var localizedTitle: String {
            switch self {
            case .all:
                return String(localized: "proactive.filter.all")
            case .unread:
                return String(localized: "proactive.filter.unread")
            case .urgent:
                return String(localized: "proactive.filter.urgent")
            }
        }
    }

    // MARK: - Private

    private let fetchNotificationsUseCase: FetchNotificationsUseCase
    private let markNotificationReadUseCase: MarkNotificationReadUseCase
    private let repository: ProactiveNotificationRepositoryProtocol
    private let logger = Logger(
        subsystem: "com.rafraf",
        category: "NotificationCenter"
    )

    // MARK: - Init

    init(
        fetchNotificationsUseCase: FetchNotificationsUseCase,
        markNotificationReadUseCase: MarkNotificationReadUseCase,
        repository: ProactiveNotificationRepositoryProtocol
    ) {
        self.fetchNotificationsUseCase = fetchNotificationsUseCase
        self.markNotificationReadUseCase = markNotificationReadUseCase
        self.repository = repository
        logger.info("NotificationCenterViewModel baslatildi")
    }

    // MARK: - Actions

    /// Ilk yuklenme.
    func onAppear() async {
        await loadNotifications()
        await loadUnreadCount()
    }

    /// Bildirimleri yukle (sayfa 1).
    func loadNotifications() async {
        isLoading = true
        errorMessage = nil
        currentPage = 1

        do {
            let result = try await fetchNotificationsUseCase.execute(
                page: 1,
                pageSize: pageSize,
                priority: selectedFilter == .urgent ? .urgent : nil,
                isRead: selectedFilter == .unread ? false : nil
            )
            notifications = result.notifications
            totalCount = result.total
            hasMore = result.notifications.count < result.total
            logger.info("Bildirimler yuklendi: \(result.notifications.count)/\(result.total)")
        } catch {
            logger.error("Bildirim yukleme hatasi: \(error.localizedDescription)")
            errorMessage = String(localized: "proactive.error.loadFailed")
        }

        isLoading = false
    }

    /// Daha fazla bildirim yukle (sonraki sayfa).
    func loadMore() async {
        guard hasMore, !isLoadingMore else { return }
        isLoadingMore = true

        let nextPage = currentPage + 1
        do {
            let result = try await fetchNotificationsUseCase.execute(
                page: nextPage,
                pageSize: pageSize,
                priority: selectedFilter == .urgent ? .urgent : nil,
                isRead: selectedFilter == .unread ? false : nil
            )
            notifications.append(contentsOf: result.notifications)
            currentPage = nextPage
            hasMore = notifications.count < result.total
            logger.info("Daha fazla bildirim yuklendi: sayfa \(nextPage)")
        } catch {
            logger.error("Daha fazla bildirim yukleme hatasi: \(error.localizedDescription)")
        }

        isLoadingMore = false
    }

    /// Okunmamis bildirim sayisini yukle.
    func loadUnreadCount() async {
        do {
            unreadCount = try await repository.getUnreadCount()
        } catch {
            logger.error("Okunmamis sayi yuklenemedi: \(error.localizedDescription)")
        }
    }

    /// Bildirimi okundu isaretle.
    /// - Parameter notification: Okundu isaretlenecek bildirim.
    func markAsRead(_ notification: ProactiveNotification) async {
        guard !notification.isRead else { return }
        do {
            let updated = try await markNotificationReadUseCase.execute(
                notificationId: notification.id
            )
            if let index = notifications.firstIndex(where: { $0.id == notification.id }) {
                notifications[index] = updated
            }
            unreadCount = max(0, unreadCount - 1)
            logger.info("Bildirim okundu isaretlendi: \(notification.id)")
        } catch {
            logger.error("Okundu isaretleme hatasi: \(error.localizedDescription)")
        }
    }

    /// Tum bildirimleri okundu isaretle.
    func markAllAsRead() async {
        do {
            let count = try await markNotificationReadUseCase.executeAll()
            // Listeyi guncelle
            notifications = notifications.map { notification in
                guard !notification.isRead else { return notification }
                return ProactiveNotification(
                    id: notification.id,
                    type: notification.type,
                    priority: notification.priority,
                    title: notification.title,
                    body: notification.body,
                    source: notification.source,
                    sourceEvent: notification.sourceEvent,
                    deepLink: notification.deepLink,
                    metadata: notification.metadata,
                    isRead: true,
                    readAt: Date(),
                    createdAt: notification.createdAt
                )
            }
            unreadCount = 0
            logger.info("Tum bildirimler okundu isaretlendi: \(count)")
        } catch {
            logger.error("Tumunu okundu isaretleme hatasi: \(error.localizedDescription)")
        }
    }

    /// Bildirimi sil.
    /// - Parameter notification: Silinecek bildirim.
    func deleteNotification(_ notification: ProactiveNotification) async {
        do {
            try await repository.deleteNotification(notificationId: notification.id)
            notifications.removeAll { $0.id == notification.id }
            totalCount -= 1
            if !notification.isRead {
                unreadCount = max(0, unreadCount - 1)
            }
            logger.info("Bildirim silindi: \(notification.id)")
        } catch {
            logger.error("Bildirim silme hatasi: \(error.localizedDescription)")
        }
    }

    /// Filtre degistir.
    /// - Parameter filter: Yeni filtre.
    func changeFilter(_ filter: NotificationFilter) async {
        selectedFilter = filter
        await loadNotifications()
    }
}
