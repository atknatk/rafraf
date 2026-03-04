import SwiftUI

/// Shimmer/skeleton loading efekti.
/// Yukleme durumunda icerige parlak gradient animasyonu uygular.
struct RFShimmerModifier: ViewModifier {
    let isActive: Bool
    @State private var phase: CGFloat = -1.0

    func body(content: Content) -> some View {
        if isActive {
            content
                .redacted(reason: .placeholder)
                .overlay {
                    GeometryReader { geometry in
                        LinearGradient(
                            colors: [
                                .clear,
                                Color.white.opacity(0.4),
                                .clear
                            ],
                            startPoint: .leading,
                            endPoint: .trailing
                        )
                        .frame(width: geometry.size.width * 0.6)
                        .offset(x: phase * geometry.size.width)
                    }
                    .clipped()
                }
                .onAppear {
                    withAnimation(
                        .linear(duration: 1.2)
                        .repeatForever(autoreverses: false)
                    ) {
                        phase = 1.5
                    }
                }
        } else {
            content
        }
    }
}

extension View {
    /// Shimmer yukleme efekti uygular.
    func rfShimmer(isActive: Bool) -> some View {
        modifier(RFShimmerModifier(isActive: isActive))
    }
}
