import SwiftUI

/// In-app bildirim banner bileseni.
/// Uygulama on plandayken gelen bildirimleri ekranin ustunde gosterir.
struct RFNotificationBanner: View {
    let notification: PushNotification
    let onTap: () -> Void
    let onDismiss: () -> Void

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: RFSpacing.sm) {
                Image(systemName: notification.category.iconName)
                    .font(.title3)
                    .foregroundStyle(iconColor)

                VStack(alignment: .leading, spacing: RFSpacing.xxs) {
                    RFText(notification.title, style: .bodyBold)
                        .lineLimit(1)
                    RFText(notification.body, style: .caption)
                        .lineLimit(2)
                }

                Spacer()

                RFButton(
                    String(localized: "notification.banner.dismiss"),
                    style: .ghost,
                    size: .small
                ) {
                    onDismiss()
                }
            }
            .padding(RFSpacing.md)
            .background(RFColors.fallbackSurface)
            .clipShape(RoundedRectangle(cornerRadius: 16))
            .shadow(color: .black.opacity(0.15), radius: 8, y: 4)
        }
        .padding(.horizontal, RFSpacing.md)
        .onTapGesture {
            onTap()
        }
        .transition(.move(edge: .top).combined(with: .opacity))
    }

    private var iconColor: Color {
        switch notification.category {
        case .taskComplete:
            return RFColors.success
        case .approvalNeeded:
            return RFColors.warning
        case .error:
            return RFColors.error
        case .info:
            return RFColors.info
        }
    }
}

#Preview {
    VStack {
        RFNotificationBanner(
            notification: PushNotification(
                id: UUID(),
                category: .taskComplete,
                title: "Gorev Tamamlandi",
                body: "Proje X basariyla deploy edildi.",
                deepLink: nil,
                badgeCount: 0,
                receivedAt: Date()
            ),
            onTap: {},
            onDismiss: {}
        )

        RFNotificationBanner(
            notification: PushNotification(
                id: UUID(),
                category: .approvalNeeded,
                title: "Onay Gerekiyor",
                body: "Proje Y production deploy onayinizi bekliyor.",
                deepLink: "rafraf://approval/123",
                badgeCount: 1,
                receivedAt: Date()
            ),
            onTap: {},
            onDismiss: {}
        )
    }
}
