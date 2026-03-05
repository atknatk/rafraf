import SwiftUI

/// Proje durum gostergesi bileseni.
/// Projenin aktif, beklemede veya tamamlandi durumunu gorsel olarak gosterir.
struct RFProjectStatusBadge: View {
    let status: ProjectStatus
    @State private var isPulsing = false

    var body: some View {
        HStack(spacing: RFSpacing.xxs) {
            ZStack {
                if status == .active {
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
            if status == .active {
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
        case .active:
            return RFColors.success
        case .pending:
            return RFColors.warning
        case .completed:
            return RFColors.info
        case .archived:
            return RFColors.fallbackTextSecondary
        }
    }

    private var statusText: String {
        switch status {
        case .active:
            return String(localized: "project.status.active")
        case .pending:
            return String(localized: "project.status.pending")
        case .completed:
            return String(localized: "project.status.completed")
        case .archived:
            return String(localized: "project.status.archived")
        }
    }
}

#Preview {
    VStack(spacing: RFSpacing.md) {
        RFProjectStatusBadge(status: .active)
        RFProjectStatusBadge(status: .pending)
        RFProjectStatusBadge(status: .completed)
    }
    .padding()
}
