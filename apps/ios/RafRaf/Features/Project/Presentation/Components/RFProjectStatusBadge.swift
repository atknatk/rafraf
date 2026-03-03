import SwiftUI

/// Proje durum gostergesi bileseni.
/// Projenin aktif, beklemede veya tamamlandi durumunu gorsel olarak gosterir.
struct RFProjectStatusBadge: View {
    let status: ProjectStatus

    var body: some View {
        HStack(spacing: RFSpacing.xxs) {
            Circle()
                .fill(statusColor)
                .frame(width: 8, height: 8)

            RFText(statusText, style: .captionBold, color: statusColor)
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
