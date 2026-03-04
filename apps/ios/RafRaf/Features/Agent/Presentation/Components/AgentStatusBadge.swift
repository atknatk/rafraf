import SwiftUI

/// Agent durum gostergesi bileseni.
/// Agent'in online, offline veya busy durumunu gorsel olarak gosterir.
struct AgentStatusBadge: View {
    let status: AgentStatus
    @State private var isPulsing = false

    var body: some View {
        HStack(spacing: RFSpacing.xxs) {
            ZStack {
                if status == .online {
                    Circle()
                        .fill(statusColor.opacity(0.3))
                        .frame(width: 12, height: 12)
                        .scaleEffect(isPulsing ? 1.5 : 1.0)
                        .opacity(isPulsing ? 0 : 0.5)
                        .animation(
                            .easeInOut(duration: 1.5)
                            .repeatForever(autoreverses: false),
                            value: isPulsing
                        )
                }

                Circle()
                    .fill(statusColor)
                    .frame(width: 8, height: 8)
            }

            RFText(statusText, style: .captionBold, color: statusColor)
        }
        .onAppear {
            if status == .online {
                isPulsing = true
            }
        }
        .padding(.horizontal, RFSpacing.xs)
        .padding(.vertical, RFSpacing.xxs)
        .background(statusColor.opacity(0.12))
        .clipShape(Capsule())
    }

    // MARK: - Private

    private var statusColor: Color {
        switch status {
        case .online:
            return RFColors.success
        case .busy:
            return RFColors.warning
        case .offline:
            return RFColors.fallbackTextTertiary
        }
    }

    private var statusText: String {
        switch status {
        case .online:
            return String(localized: "agent.status.online")
        case .busy:
            return String(localized: "agent.status.busy")
        case .offline:
            return String(localized: "agent.status.offline")
        }
    }
}

#Preview {
    VStack(spacing: RFSpacing.md) {
        AgentStatusBadge(status: .online)
        AgentStatusBadge(status: .busy)
        AgentStatusBadge(status: .offline)
    }
    .padding()
}
