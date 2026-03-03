import SwiftUI

/// RafRaf hata goruntuleme bileseni.
/// Hata durumlari icin kullaniciya bilgilendirme ve yeniden deneme aksiyonu saglar.
struct RFErrorView: View {
    let title: String
    let message: String
    let systemImage: String
    let retryTitle: String?
    let retryAction: (() -> Void)?

    init(
        title: String = String(localized: "error.default.title"),
        message: String,
        systemImage: String = "exclamationmark.triangle",
        retryTitle: String? = String(localized: "error.retry"),
        retryAction: (() -> Void)? = nil
    ) {
        self.title = title
        self.message = message
        self.systemImage = systemImage
        self.retryTitle = retryTitle
        self.retryAction = retryAction
    }

    var body: some View {
        VStack(spacing: RFSpacing.md) {
            Image(systemName: systemImage)
                .font(.system(size: 48))
                .foregroundStyle(RFColors.error)

            RFText(title, style: .title)

            RFText(message, style: .body, color: RFColors.fallbackTextSecondary)
                .multilineTextAlignment(.center)

            if let retryTitle, let retryAction {
                RFButton(retryTitle, style: .primary, size: .medium) {
                    retryAction()
                }
                .padding(.top, RFSpacing.xs)
            }
        }
        .padding(RFSpacing.xxl)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

#Preview {
    VStack(spacing: RFSpacing.xxl) {
        RFErrorView(
            message: String(localized: "error.network.message")
        ) {
            // retry action
        }

        RFErrorView(
            title: String(localized: "error.server.title"),
            message: String(localized: "error.server.message"),
            systemImage: "server.rack",
            retryTitle: nil,
            retryAction: nil
        )
    }
}
