import SwiftUI

/// RafRaf kart stilleri.
enum RFCardStyle: Sendable {
    /// Standart kart - sadece icerik goruntuler.
    case standard
    /// Interaktif kart - tiklanabilir, press efekti ile.
    case interactive
    /// Glass kart - ultraThinMaterial arkaplan ile yari saydam.
    case glass
    /// Yukseltimlmis kart - belirgin golge ile derinlik.
    case elevated
}

/// RafRaf kart bileseni.
/// Feature ekranlarinda icerik gruplama icin kullanilir.
/// Glass stilinde yavas donen AngularGradient border ile premium his.
struct RFCard<Content: View>: View {
    let style: RFCardStyle
    let padding: CGFloat
    let cornerRadius: CGFloat
    let onTap: (() -> Void)?
    @ViewBuilder let content: () -> Content
    @State private var borderPhase: Double = 0

    init(
        style: RFCardStyle = .standard,
        padding: CGFloat = RFSpacing.md,
        cornerRadius: CGFloat = RFCornerRadius.large,
        onTap: (() -> Void)? = nil,
        @ViewBuilder content: @escaping () -> Content
    ) {
        self.style = style
        self.padding = padding
        self.cornerRadius = cornerRadius
        self.onTap = onTap
        self.content = content
    }

    var body: some View {
        Group {
            if style == .interactive, let onTap {
                Button(action: onTap) {
                    cardContent
                }
                .buttonStyle(RFPressButtonStyle())
            } else {
                cardContent
            }
        }
    }

    private var cardContent: some View {
        content()
            .padding(padding)
            .background {
                Group {
                    switch style {
                    case .glass:
                        RoundedRectangle(cornerRadius: cornerRadius)
                            .fill(.ultraThinMaterial)
                    default:
                        RFColors.fallbackSurface
                    }
                }
            }
            .clipShape(RoundedRectangle(cornerRadius: cornerRadius))
            .overlay {
                if style == .glass {
                    RoundedRectangle(cornerRadius: cornerRadius)
                        .strokeBorder(
                            AngularGradient(
                                colors: [
                                    Color.white.opacity(0.2),
                                    Color.white.opacity(0.05),
                                    Color.white.opacity(0.15),
                                    Color.white.opacity(0.05),
                                    Color.white.opacity(0.2)
                                ],
                                center: .center,
                                startAngle: .degrees(borderPhase),
                                endAngle: .degrees(borderPhase + 360)
                            ),
                            lineWidth: 0.5
                        )
                        .onAppear {
                            withAnimation(
                                .linear(duration: 7)
                                .repeatForever(autoreverses: false)
                            ) {
                                borderPhase = 360
                            }
                        }
                }
            }
            .rfElevation(cardElevation)
    }

    private var cardElevation: RFElevationLevel {
        switch style {
        case .standard: return .low
        case .interactive: return .medium
        case .glass: return .low
        case .elevated: return .high
        }
    }
}

#Preview {
    VStack(spacing: RFSpacing.md) {
        RFCard {
            VStack(alignment: .leading, spacing: RFSpacing.xs) {
                RFText("Standart Kart", style: .title)
                RFText("Bu standart bir kart bilesenidir.", style: .body)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }

        RFCard(style: .interactive, onTap: {}) {
            VStack(alignment: .leading, spacing: RFSpacing.xs) {
                RFText("Interaktif Kart", style: .title)
                RFText("Bu tiklanabilir bir kart bilesenidir.", style: .body)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }

        RFCard(style: .glass) {
            VStack(alignment: .leading, spacing: RFSpacing.xs) {
                RFText("Glass Kart", style: .title)
                RFText("Yari saydam materyal arkaplan.", style: .body)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }

        RFCard(style: .elevated) {
            VStack(alignment: .leading, spacing: RFSpacing.xs) {
                RFText("Yukseltilmis Kart", style: .title)
                RFText("Belirgin golge ile derinlik.", style: .body)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }
    .padding()
    .background(RFColors.fallbackBackground)
}
