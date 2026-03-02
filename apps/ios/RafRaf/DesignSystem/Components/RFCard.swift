import SwiftUI

/// RafRaf kart bileseni.
/// Feature ekranlarinda icerik gruplama icin kullanilir.
struct RFCard<Content: View>: View {
    let padding: CGFloat
    let cornerRadius: CGFloat
    @ViewBuilder let content: () -> Content

    init(
        padding: CGFloat = RFSpacing.md,
        cornerRadius: CGFloat = 16,
        @ViewBuilder content: @escaping () -> Content
    ) {
        self.padding = padding
        self.cornerRadius = cornerRadius
        self.content = content
    }

    var body: some View {
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
                RFText("Kart Basligi", style: .title)
                RFText("Kart icerik metni buraya gelir.", style: .body)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }

        RFCard(padding: RFSpacing.xl, cornerRadius: 24) {
            RFText("Ozel bosluklu kart", style: .body)
        }
    }
    .padding()
}
