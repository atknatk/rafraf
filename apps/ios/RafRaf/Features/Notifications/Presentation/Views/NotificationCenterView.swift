import SwiftUI

/// Bildirim merkezi ekrani.
/// Proaktif bildirimlerin listelendigi, filtrelendigi ve yonetildigi ana ekran.
struct NotificationCenterView: View {
    @State private var viewModel: NotificationCenterViewModel

    init(viewModel: NotificationCenterViewModel) {
        _viewModel = State(initialValue: viewModel)
    }

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                // Filtre segmenti
                filterBar

                // Bildirim listesi
                if viewModel.isLoading {
                    Spacer()
                    ProgressView()
                        .controlSize(.large)
                    Spacer()
                } else if viewModel.notifications.isEmpty {
                    emptyState
                } else {
                    notificationList
                }
            }
            .navigationTitle(String(localized: "proactive.title"))
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    if viewModel.unreadCount > 0 {
                        RFButton(
                            String(localized: "proactive.action.markAllRead"),
                            style: .ghost,
                            size: .small
                        ) {
                            Task {
                                await viewModel.markAllAsRead()
                            }
                        }
                    }
                }
            }
            .task {
                await viewModel.onAppear()
            }
            .refreshable {
                await viewModel.loadNotifications()
                await viewModel.loadUnreadCount()
            }
        }
    }

    // MARK: - Subviews

    private var filterBar: some View {
        HStack(spacing: RFSpacing.sm) {
            ForEach(
                NotificationCenterViewModel.NotificationFilter.allCases,
                id: \.rawValue
            ) { filter in
                RFButton(
                    filter.localizedTitle,
                    style: viewModel.selectedFilter == filter ? .primary : .ghost,
                    size: .small
                ) {
                    Task {
                        await viewModel.changeFilter(filter)
                    }
                }
            }
            Spacer()

            // Okunmamis sayac
            if viewModel.unreadCount > 0 {
                RFText(
                    String(viewModel.unreadCount),
                    style: .caption
                )
                .padding(.horizontal, RFSpacing.xs)
                .padding(.vertical, 2)
                .background(RFColors.primary)
                .foregroundStyle(.white)
                .clipShape(Capsule())
            }
        }
        .padding(.horizontal, RFSpacing.md)
        .padding(.vertical, RFSpacing.sm)
    }

    private var notificationList: some View {
        ScrollView {
            LazyVStack(spacing: RFSpacing.sm) {
                ForEach(viewModel.notifications) { notification in
                    RFProactiveNotificationCard(
                        notification: notification,
                        onTap: {
                            Task {
                                await viewModel.markAsRead(notification)
                            }
                        },
                        onDelete: {
                            Task {
                                await viewModel.deleteNotification(notification)
                            }
                        }
                    )
                }

                // Load more
                if viewModel.hasMore {
                    if viewModel.isLoadingMore {
                        ProgressView()
                            .padding()
                    } else {
                        Color.clear
                            .frame(height: 1)
                            .onAppear {
                                Task {
                                    await viewModel.loadMore()
                                }
                            }
                    }
                }
            }
            .padding(.horizontal, RFSpacing.md)
            .padding(.top, RFSpacing.sm)
        }
    }

    private var emptyState: some View {
        VStack(spacing: RFSpacing.md) {
            Spacer()
            Image(systemName: "bell.slash")
                .font(.system(size: 48))
                .foregroundStyle(.secondary)
            RFText(
                String(localized: "proactive.empty.title"),
                style: .body
            )
            .foregroundStyle(.secondary)
            RFText(
                String(localized: "proactive.empty.description"),
                style: .caption
            )
            .foregroundStyle(.tertiary)
            .multilineTextAlignment(.center)
            Spacer()
        }
        .padding(RFSpacing.lg)
    }
}

#Preview {
    NotificationCenterView(
        viewModel: NotificationCenterViewModel(
            fetchNotificationsUseCase: FetchNotificationsUseCase(
                repository: PreviewProactiveNotificationRepository()
            ),
            markNotificationReadUseCase: MarkNotificationReadUseCase(
                repository: PreviewProactiveNotificationRepository()
            ),
            repository: PreviewProactiveNotificationRepository()
        )
    )
}

/// Preview icin mock repository.
private final class PreviewProactiveNotificationRepository: ProactiveNotificationRepositoryProtocol, @unchecked Sendable {
    func getNotifications(
        page: Int,
        pageSize: Int,
        priority: NotificationPriority?,
        isRead: Bool?,
        type: ProactiveNotificationType?
    ) async throws -> ProactiveNotificationListResult {
        ProactiveNotificationListResult(
            notifications: [
                ProactiveNotification(
                    id: UUID(),
                    type: .prMerged,
                    priority: .normal,
                    title: "PR #42 merged",
                    body: "feat(backend): WebSocket auth eklendi",
                    source: "github",
                    sourceEvent: nil,
                    deepLink: nil,
                    metadata: [:],
                    isRead: false,
                    readAt: nil,
                    createdAt: Date().addingTimeInterval(-300)
                ),
                ProactiveNotification(
                    id: UUID(),
                    type: .ciFailure,
                    priority: .urgent,
                    title: "CI Failed",
                    body: "main branch CI basarisiz",
                    source: "github",
                    sourceEvent: nil,
                    deepLink: nil,
                    metadata: [:],
                    isRead: true,
                    readAt: Date(),
                    createdAt: Date().addingTimeInterval(-3600)
                )
            ],
            total: 2,
            page: 1,
            pageSize: 20
        )
    }

    func markAsRead(notificationId: UUID) async throws -> ProactiveNotification {
        ProactiveNotification(
            id: notificationId,
            type: .prMerged,
            priority: .normal,
            title: "Test",
            body: "Test",
            source: "test",
            sourceEvent: nil,
            deepLink: nil,
            metadata: [:],
            isRead: true,
            readAt: Date(),
            createdAt: Date()
        )
    }

    func markAllAsRead() async throws -> Int { 2 }

    func deleteNotification(notificationId: UUID) async throws {}

    func getUnreadCount() async throws -> Int { 1 }
}
