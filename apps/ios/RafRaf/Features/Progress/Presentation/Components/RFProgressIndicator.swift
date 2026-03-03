import SwiftUI

/// RafRaf progress indicator bileseni.
/// Determinate (yuzdeli) ve indeterminate (suresiz) modlari destekler.
/// AI islem sirasinda kullaniciya gorsel geri bildirim saglar.
struct RFProgressIndicator: View {
    /// Ilerleme modu.
    let mode: ProgressMode
    /// Ilerleme yuzdesi (0.0 - 1.0, sadece determinate modda).
    let progress: Double
    /// Gosterge mesaji.
    let message: String?
    /// Compact gorunum (sadece bar + mesaj).
    let isCompact: Bool

    @State private var rotationAngle: Double = 0
    @State private var pulseScale: Double = 1.0

    init(
        mode: ProgressMode = .indeterminate,
        progress: Double = 0,
        message: String? = nil,
        isCompact: Bool = false
    ) {
        self.mode = mode
        self.progress = progress
        self.message = message
        self.isCompact = isCompact
    }

    var body: some View {
        VStack(spacing: isCompact ? RFSpacing.xs : RFSpacing.md) {
            progressBar

            if let message {
                RFText(message, style: .caption)
                    .lineLimit(1)
            }
        }
    }

    // MARK: - Private Views

    @ViewBuilder
    private var progressBar: some View {
        switch mode {
        case .determinate:
            determinateBar
        case .indeterminate:
            indeterminateBar
        }
    }

    private var determinateBar: some View {
        VStack(spacing: RFSpacing.xxs) {
            GeometryReader { geometry in
                ZStack(alignment: .leading) {
                    // Arkaplan
                    RoundedRectangle(cornerRadius: 4)
                        .fill(RFColors.fallbackSurface)
                        .frame(height: isCompact ? 4 : 6)

                    // Ilerleme
                    RoundedRectangle(cornerRadius: 4)
                        .fill(RFColors.fallbackPrimary)
                        .frame(
                            width: max(0, geometry.size.width * progress),
                            height: isCompact ? 4 : 6
                        )
                        .animation(.easeInOut(duration: 0.3), value: progress)
                }
            }
            .frame(height: isCompact ? 4 : 6)

            if !isCompact {
                HStack {
                    Spacer()
                    RFText(
                        String(localized: "progress.percentage.\(Int(progress * 100))"),
                        style: .captionBold
                    )
                }
            }
        }
    }

    private var indeterminateBar: some View {
        GeometryReader { geometry in
            ZStack(alignment: .leading) {
                // Arkaplan
                RoundedRectangle(cornerRadius: 4)
                    .fill(RFColors.fallbackSurface)
                    .frame(height: isCompact ? 4 : 6)

                // Animasyonlu parca
                RoundedRectangle(cornerRadius: 4)
                    .fill(RFColors.fallbackPrimary)
                    .frame(
                        width: geometry.size.width * 0.3,
                        height: isCompact ? 4 : 6
                    )
                    .offset(x: indeterminateOffset(width: geometry.size.width))
                    .animation(
                        .easeInOut(duration: 1.5).repeatForever(autoreverses: true),
                        value: pulseScale
                    )
            }
        }
        .frame(height: isCompact ? 4 : 6)
        .onAppear {
            pulseScale = 2.0
        }
    }

    private func indeterminateOffset(width: CGFloat) -> CGFloat {
        let maxOffset = width * 0.7
        return pulseScale > 1.5 ? maxOffset : 0
    }
}

#Preview {
    VStack(spacing: RFSpacing.xl) {
        RFProgressIndicator(
            mode: .determinate,
            progress: 0.65,
            message: String(localized: "progress.preview.building")
        )

        RFProgressIndicator(
            mode: .indeterminate,
            message: String(localized: "progress.preview.thinking")
        )

        RFProgressIndicator(
            mode: .determinate,
            progress: 0.3,
            isCompact: true
        )

        RFProgressIndicator(
            mode: .indeterminate,
            isCompact: true
        )
    }
    .padding()
}
