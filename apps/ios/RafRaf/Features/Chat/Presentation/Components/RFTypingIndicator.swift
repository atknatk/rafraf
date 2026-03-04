import SwiftUI

/// AI yaziyor gostergesi.
/// TimelineView ile surekli sin() dalga animasyonu — organik "dusunuyor" hissi.
struct RFTypingIndicator: View {
    private let dotSize: CGFloat = 6

    var body: some View {
        HStack(spacing: 0) {
            TimelineView(.animation) { timeline in
                dotsView(phase: timeline.date.timeIntervalSinceReferenceDate)
            }
            .padding(.horizontal, RFSpacing.md)
            .padding(.vertical, RFSpacing.sm)
            .background(RFColors.aiBubble)
            .clipShape(RoundedRectangle(cornerRadius: 16))

            Spacer()
        }
    }

    private func dotsView(phase: Double) -> some View {
        HStack(spacing: RFSpacing.xxs) {
            ForEach(0..<3, id: \.self) { index in
                dotView(phase: phase, index: index)
            }
        }
    }

    private func dotView(phase: Double, index: Int) -> some View {
        let wave = sin(phase * 3.5 + Double(index) * 0.8)
        return Circle()
            .fill(RFColors.fallbackTextSecondary)
            .frame(width: dotSize, height: dotSize)
            .offset(y: wave * 4)
            .scaleEffect(1.0 + wave * 0.15)
    }
}

#Preview {
    VStack(spacing: RFSpacing.md) {
        RFTypingIndicator()
    }
    .padding()
}
