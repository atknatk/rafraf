import SwiftUI

/// Yavas hareket eden animasyonlu gradient arkaplan.
/// Auth ekranlarinda premium ilk izlenim icin kullanilir.
/// Gradient baslangic/bitis noktalari yavasca kayar.
struct RFAnimatedGradientBackground: View {
    @State private var animationPhase: CGFloat = 0

    var body: some View {
        TimelineView(.animation(minimumInterval: 1.0 / 30.0)) { timeline in
            let phase = timeline.date.timeIntervalSinceReferenceDate * 0.08

            LinearGradient(
                colors: [RFColors.heroGradientStart, RFColors.heroGradientEnd],
                startPoint: startPoint(phase: phase),
                endPoint: endPoint(phase: phase)
            )
        }
        .ignoresSafeArea()
    }

    private func startPoint(phase: Double) -> UnitPoint {
        UnitPoint(
            x: 0.5 + 0.2 * sin(phase),
            y: 0.0 + 0.1 * cos(phase * 0.7)
        )
    }

    private func endPoint(phase: Double) -> UnitPoint {
        UnitPoint(
            x: 0.5 + 0.2 * cos(phase * 0.5),
            y: 1.0 + 0.1 * sin(phase * 0.8)
        )
    }
}

#Preview {
    ZStack {
        RFAnimatedGradientBackground()

        VStack {
            RFText("Animated Background", style: .title)
        }
    }
}
