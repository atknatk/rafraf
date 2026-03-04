import SwiftUI

/// Glass material bar bileseni.
/// Chat input ve alt bar'lar icin yari saydam materyal arkaplan saglar.
struct RFGlassBar<Content: View>: View {
    @ViewBuilder let content: () -> Content

    var body: some View {
        VStack(spacing: 0) {
            Divider()
            content()
                .padding(.horizontal, RFSpacing.md)
                .padding(.vertical, RFSpacing.sm)
                .background(.ultraThinMaterial)
        }
    }
}

#Preview {
    VStack {
        Spacer()
        RFGlassBar {
            HStack {
                RFText("Glass Bar Preview", style: .body)
                Spacer()
                Image(systemName: "arrow.up.circle.fill")
                    .foregroundStyle(RFColors.fallbackPrimary)
            }
        }
    }
    .background(
        LinearGradient(
            colors: [RFColors.heroGradientStart, RFColors.heroGradientEnd],
            startPoint: .top,
            endPoint: .bottom
        )
    )
}
