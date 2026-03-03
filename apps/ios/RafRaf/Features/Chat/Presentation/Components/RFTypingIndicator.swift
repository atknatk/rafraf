import SwiftUI

/// AI yaziyor gostergesi.
/// Uc noktali animasyonlu gosterge.
struct RFTypingIndicator: View {
    @State private var animationPhase: Int = 0

    private let dotSize: CGFloat = 6
    private let animationDuration: Double = 0.4

    var body: some View {
        HStack(spacing: 0) {
            HStack(spacing: RFSpacing.xxs) {
                typingDots
            }
            .padding(.horizontal, RFSpacing.md)
            .padding(.vertical, RFSpacing.sm)
            .background(RFColors.aiBubble)
            .clipShape(RoundedRectangle(cornerRadius: 16))

            Spacer()
        }
        .onAppear {
            startAnimation()
        }
    }

    private var typingDots: some View {
        ForEach(0..<3, id: \.self) { index in
            Circle()
                .fill(RFColors.fallbackTextSecondary)
                .frame(width: dotSize, height: dotSize)
                .offset(y: animationPhase == index ? -4 : 0)
                .animation(
                    .easeInOut(duration: animationDuration)
                        .repeatForever(autoreverses: true)
                        .delay(Double(index) * 0.15),
                    value: animationPhase
                )
        }
    }

    private func startAnimation() {
        withAnimation {
            animationPhase = 2
        }
    }
}

#Preview {
    VStack(spacing: RFSpacing.md) {
        RFTypingIndicator()
    }
    .padding()
}
