import SwiftUI

/// Ses seviyesi dalga formu gostergesi.
/// Kayit sirasinda canli ses seviyesini gorsellestirir.
struct RFWaveformView: View {
    let audioLevel: Float
    let barCount: Int
    let isActive: Bool

    @State private var animatedLevels: [Float] = []

    init(audioLevel: Float, barCount: Int = 20, isActive: Bool = true) {
        self.audioLevel = audioLevel
        self.barCount = barCount
        self.isActive = isActive
    }

    var body: some View {
        HStack(spacing: 2) {
            ForEach(0..<barCount, id: \.self) { index in
                RoundedRectangle(cornerRadius: 2)
                    .fill(barColor(for: index))
                    .frame(width: 3, height: barHeight(for: index))
                    .animation(.easeInOut(duration: 0.1), value: audioLevel)
            }
        }
        .frame(height: maxBarHeight)
        .onChange(of: audioLevel) {
            updateLevels()
        }
        .onAppear {
            animatedLevels = Array(repeating: 0, count: barCount)
        }
    }

    // MARK: - Private

    private var maxBarHeight: CGFloat { 40 }
    private var minBarHeight: CGFloat { 4 }

    private func barHeight(for index: Int) -> CGFloat {
        guard isActive, index < animatedLevels.count else {
            return minBarHeight
        }
        let level = CGFloat(animatedLevels[index])
        return minBarHeight + (maxBarHeight - minBarHeight) * level
    }

    private func barColor(for index: Int) -> Color {
        guard isActive else {
            return RFColors.fallbackTextTertiary.opacity(0.3)
        }
        let level = index < animatedLevels.count ? CGFloat(animatedLevels[index]) : 0
        return RFColors.fallbackPrimary.opacity(0.4 + level * 0.6)
    }

    private func updateLevels() {
        guard animatedLevels.count == barCount else {
            animatedLevels = Array(repeating: 0, count: barCount)
            return
        }

        // Seviyeleri sola kaydir (scroll efekti)
        for index in 0..<(barCount - 1) {
            animatedLevels[index] = animatedLevels[index + 1]
        }

        // Son bar'a yeni seviyeyi ekle (kuucuk randomluk ile dogal gorunum)
        let variation = Float.random(in: -0.1...0.1)
        let newLevel = max(0, min(1, audioLevel + variation))
        animatedLevels[barCount - 1] = newLevel
    }
}

#Preview {
    VStack(spacing: RFSpacing.lg) {
        RFWaveformView(audioLevel: 0.0, isActive: false)
        RFWaveformView(audioLevel: 0.3, isActive: true)
        RFWaveformView(audioLevel: 0.7, isActive: true)
        RFWaveformView(audioLevel: 1.0, isActive: true)
    }
    .padding()
}
