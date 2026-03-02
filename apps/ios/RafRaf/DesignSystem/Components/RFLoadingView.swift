import SwiftUI

/// RafRaf yukleme gostergesi bileseni.
/// Async islemler sirasinda kullaniciya geri bildirim saglar.
struct RFLoadingView: View {
    let message: String?

    init(message: String? = nil) {
        self.message = message
    }

    var body: some View {
        VStack(spacing: RFSpacing.md) {
            ProgressView()
                .controlSize(.large)

            if let message {
                RFText(message, style: .caption)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

#Preview {
    VStack(spacing: RFSpacing.xl) {
        RFLoadingView()
        RFLoadingView(message: String(localized: "loading.message"))
    }
}
