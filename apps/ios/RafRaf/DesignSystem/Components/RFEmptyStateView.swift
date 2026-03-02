import SwiftUI

/// RafRaf bos durum bileseni.
/// Liste veya icerik bos oldugunda gosterilir.
struct RFEmptyStateView: View {
    let systemImage: String
    let title: String
    let message: String
    let actionTitle: String?
    let action: (() -> Void)?

    init(
        systemImage: String,
        title: String,
        message: String,
        actionTitle: String? = nil,
        action: (() -> Void)? = nil
    ) {
        self.systemImage = systemImage
        self.title = title
        self.message = message
        self.actionTitle = actionTitle
        self.action = action
    }

    var body: some View {
        VStack(spacing: RFSpacing.md) {
            Image(systemName: systemImage)
                .font(.system(size: 48))
                .foregroundStyle(RFColors.fallbackTextSecondary)

            RFText(title, style: .title)

            RFText(message, style: .body, color: RFColors.fallbackTextSecondary)
                .multilineTextAlignment(.center)

            if let actionTitle, let action {
                RFButton(actionTitle, style: .primary, size: .medium) {
                    action()
                }
                .padding(.top, RFSpacing.xs)
            }
        }
        .padding(RFSpacing.xxl)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

#Preview {
    RFEmptyStateView(
        systemImage: "tray",
        title: "Henuz icerik yok",
        message: "Yeni bir proje olusturarak baslayin.",
        actionTitle: "Proje Olustur"
    ) {
        // action
    }
}
