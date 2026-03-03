import SwiftUI

/// RafRaf kart stilleri.
enum RFCardStyle: Sendable {
    /// Standart kart - sadece icerik goruntuler.
    case standard
    /// Interaktif kart - tiklanabilir, hover efekti ile.
    case interactive
}

/// RafRaf kart bileseni.
/// Feature ekranlarinda icerik gruplama icin kullanilir.
struct RFCard<Content: View>: View {
    let style: RFCardStyle
    let padding: CGFloat
    let cornerRadius: CGFloat
    let onTap: (() -> Void)?
    @ViewBuilder let content: () -> Content

    init(
        style: RFCardStyle = .standard,
        padding: CGFloat = RFSpacing.md,
        cornerRadius: CGFloat = 16,
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
                .buttonStyle(.plain)
            } else {
                cardContent
            }
        }
    }

    private var cardContent: some View {
        content()
            .padding(padding)
            .background(RFColors.fallbackSurface)
            .clipShape(RoundedRectangle(cornerRadius: cornerRadius))
            .shadow(color: .black.opacity(0.05), radius: 2, x: 0, y: 1)
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

        RFCard(padding: RFSpacing.xl, cornerRadius: 24) {
            RFText("Ozel bosluklu kart", style: .body)
        }
    }
    .padding()
}
