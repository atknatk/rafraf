import SwiftUI

/// Ses oynatma ilerleme cubugu.
/// Oynatma ilerlemesini ve toplam sureyi gosterir.
struct RFPlaybackProgressBar: View {
    let progress: Double
    let isActive: Bool

    var body: some View {
        GeometryReader { geometry in
            ZStack(alignment: .leading) {
                // Arkaplan
                RoundedRectangle(cornerRadius: 2)
                    .fill(RFColors.fallbackSurface)
                    .frame(height: 4)

                // Ilerleme
                RoundedRectangle(cornerRadius: 2)
                    .fill(RFColors.fallbackPrimary)
                    .frame(
                        width: geometry.size.width * min(max(progress, 0), 1),
                        height: 4
                    )
                    .animation(.linear(duration: 0.1), value: progress)
            }
        }
        .frame(height: 4)
        .opacity(isActive ? 1 : 0)
        .animation(.easeInOut(duration: 0.2), value: isActive)
        .accessibilityLabel(
            Text(String(localized: "voiceOutput.progress.label"))
        )
        .accessibilityValue(Text("\(Int(progress * 100))%"))
    }
}

#Preview {
    VStack(spacing: RFSpacing.lg) {
        RFPlaybackProgressBar(progress: 0.0, isActive: true)
        RFPlaybackProgressBar(progress: 0.3, isActive: true)
        RFPlaybackProgressBar(progress: 0.7, isActive: true)
        RFPlaybackProgressBar(progress: 1.0, isActive: true)
        RFPlaybackProgressBar(progress: 0.5, isActive: false)
    }
    .padding()
}
