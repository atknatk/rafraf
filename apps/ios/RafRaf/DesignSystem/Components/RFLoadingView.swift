import SwiftUI

/// RafRaf yukleme gostergesi bileseni.
/// Async islemler sirasinda kullaniciya geri bildirim saglar.
/// Markali gradient donen cember animasyonu.
struct RFLoadingView: View {
    let message: String?

    @State private var isAnimating = false

    init(message: String? = nil) {
        self.message = message
    }

    var body: some View {
        VStack(spacing: RFSpacing.md) {
            ZStack {
                Circle()
                    .stroke(
                        RFColors.fallbackPrimary.opacity(0.15),
                        lineWidth: 3
                    )
                    .frame(width: 44, height: 44)

                Circle()
                    .trim(from: 0, to: 0.7)
                    .stroke(
                        RFColors.brandGradient,
                        style: StrokeStyle(lineWidth: 3, lineCap: .round)
                    )
                    .frame(width: 44, height: 44)
                    .rotationEffect(.degrees(isAnimating ? 360 : 0))
                    .animation(
                        .linear(duration: 1).repeatForever(autoreverses: false),
                        value: isAnimating
                    )
            }

            if let message {
                RFText(message, style: .caption)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .onAppear {
            isAnimating = true
        }
    }
}

#Preview {
    VStack(spacing: RFSpacing.xl) {
        RFLoadingView()
        RFLoadingView(message: "Yukleniyor...")
    }
}
