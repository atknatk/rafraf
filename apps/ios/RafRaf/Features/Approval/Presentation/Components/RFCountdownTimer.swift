import SwiftUI

/// Geri sayim zamanlayici gorsel componenti.
/// Dairesel ilerleme gostergesi ve kalan sure metni ile geri sayimi gosterir.
struct RFCountdownTimer: View {
    /// Kalan sure (saniye).
    let remainingSeconds: Int
    /// Ilerleme orani (0.0 - 1.0).
    let progress: Double
    /// Tehlikeli kategori gostergesi (kirmizi renk icin).
    let isDangerous: Bool

    var body: some View {
        ZStack {
            // Arkaplan halka
            Circle()
                .stroke(
                    RFColors.fallbackSurface,
                    lineWidth: 4
                )

            // Ilerleme halkasi
            Circle()
                .trim(from: 0, to: progress)
                .stroke(
                    progressColor,
                    style: StrokeStyle(lineWidth: 4, lineCap: .round)
                )
                .rotationEffect(.degrees(-90))
                .animation(.linear(duration: 1), value: progress)

            // Kalan sure metni
            RFText(
                timeText,
                style: .captionBold,
                color: progressColor
            )
        }
        .frame(width: 48, height: 48)
        .accessibilityLabel(
            String(localized: "approval.countdown.remaining \(remainingSeconds)")
        )
    }

    // MARK: - Private

    private var timeText: String {
        if remainingSeconds >= 60 {
            let minutes = remainingSeconds / 60
            let seconds = remainingSeconds % 60
            return String(format: "%d:%02d", minutes, seconds)
        }
        return "\(remainingSeconds)"
    }

    private var progressColor: Color {
        if isDangerous || progress < 0.25 {
            return RFColors.error
        } else if progress < 0.5 {
            return RFColors.warning
        }
        return RFColors.fallbackPrimary
    }
}

#Preview {
    VStack(spacing: RFSpacing.lg) {
        RFCountdownTimer(
            remainingSeconds: 25,
            progress: 0.83,
            isDangerous: false
        )

        RFCountdownTimer(
            remainingSeconds: 10,
            progress: 0.33,
            isDangerous: false
        )

        RFCountdownTimer(
            remainingSeconds: 5,
            progress: 0.17,
            isDangerous: true
        )

        RFCountdownTimer(
            remainingSeconds: 90,
            progress: 0.75,
            isDangerous: false
        )
    }
    .padding()
}
