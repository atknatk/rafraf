import SwiftUI

/// Proaktif bildirim kart bileseni.
/// Tek bir proaktif bildirimi gosterir.
struct RFProactiveNotificationCard: View {
    let notification: ProactiveNotification
    let onTap: () -> Void
    let onDelete: () -> Void

    var body: some View {
        HStack(alignment: .top, spacing: RFSpacing.sm) {
            // Tip ikonu
            Image(systemName: notification.type.iconName)
                .font(.title3)
                .foregroundStyle(iconColor)
                .frame(width: 32, height: 32)

            VStack(alignment: .leading, spacing: RFSpacing.xxs) {
                // Baslik satiri
                HStack {
                    RFText(notification.title, style: .bodyBold)
                        .lineLimit(1)
                        .opacity(notification.isRead ? 0.6 : 1.0)

                    Spacer()

                    // Oncelik badge
                    if notification.priority == .urgent {
                        RFText(
                            String(localized: "proactive.priority.urgent"),
                            style: .caption
                        )
                        .padding(.horizontal, RFSpacing.xs)
                        .padding(.vertical, 2)
                        .background(RFColors.error.opacity(0.15))
                        .foregroundStyle(RFColors.error)
                        .clipShape(Capsule())
                    }
                }

                // Govde
                RFText(notification.body, style: .body)
                    .lineLimit(2)
                    .opacity(notification.isRead ? 0.5 : 0.8)

                // Kaynak ve zaman
                HStack(spacing: RFSpacing.xs) {
                    RFText(notification.source, style: .caption)
                        .foregroundStyle(.secondary)

                    RFText("·", style: .caption)
                        .foregroundStyle(.secondary)

                    RFText(
                        notification.createdAt.formatted(.relative(presentation: .named)),
                        style: .caption
                    )
                    .foregroundStyle(.secondary)
                }
            }

            // Okunmamis indicator
            if !notification.isRead {
                Circle()
                    .fill(RFColors.primary)
                    .frame(width: 8, height: 8)
            }
        }
        .padding(RFSpacing.md)
        .background(notification.isRead ? RFColors.fallbackSurface.opacity(0.5) : RFColors.fallbackSurface)
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .contentShape(Rectangle())
        .onTapGesture {
            onTap()
        }
        .swipeActions(edge: .trailing) {
            Button(role: .destructive) {
                onDelete()
            } label: {
                Label(
                    String(localized: "proactive.action.delete"),
                    systemImage: "trash"
                )
            }
        }
    }

    private var iconColor: Color {
        switch notification.type {
        case .taskComplete:
            return RFColors.success
        case .issueDetected, .ciFailure:
            return RFColors.error
        case .suggestion:
            return RFColors.warning
        case .reminder:
            return RFColors.info
        case .prMerged:
            return RFColors.success
        case .securityAlert:
            return RFColors.error
        }
    }
}

#Preview {
    VStack(spacing: 12) {
        RFProactiveNotificationCard(
            notification: ProactiveNotification(
                id: UUID(),
                type: .prMerged,
                priority: .normal,
                title: "PR #42 merged",
                body: "feat(backend): WebSocket auth eklendi — atknatk/rafraf",
                source: "github",
                sourceEvent: nil,
                deepLink: nil,
                metadata: [:],
                isRead: false,
                readAt: nil,
                createdAt: Date().addingTimeInterval(-300)
            ),
            onTap: {},
            onDelete: {}
        )

        RFProactiveNotificationCard(
            notification: ProactiveNotification(
                id: UUID(),
                type: .ciFailure,
                priority: .urgent,
                title: "CI Failed",
                body: "main branch CI pipeline basarisiz oldu",
                source: "github",
                sourceEvent: nil,
                deepLink: nil,
                metadata: [:],
                isRead: true,
                readAt: Date(),
                createdAt: Date().addingTimeInterval(-3600)
            ),
            onTap: {},
            onDelete: {}
        )
    }
    .padding()
}
