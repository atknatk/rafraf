import SwiftUI

/// Baglanti kalite gostergesi — kucuk renkli nokta + gecikme.
struct RFConnectionIndicator: View {
    let quality: ConnectionQualityMonitor.Quality
    let latencyMs: Int

    @State private var isPulsing = false

    var indicatorColor: Color {
        switch quality {
        case .excellent, .good: return .green
        case .fair: return .yellow
        case .poor: return .red
        case .disconnected: return .gray
        }
    }

    var body: some View {
        HStack(spacing: 4) {
            ZStack {
                Circle()
                    .fill(indicatorColor.opacity(0.3))
                    .frame(width: 12, height: 12)
                    .scaleEffect(isPulsing ? 1.4 : 1.0)
                    .animation(
                        quality == .disconnected ? .none :
                        .easeInOut(duration: 1.2).repeatForever(autoreverses: true),
                        value: isPulsing
                    )
                Circle()
                    .fill(indicatorColor)
                    .frame(width: 7, height: 7)
            }

            if latencyMs > 0 {
                Text("\(latencyMs)ms")
                    .font(.system(size: 10, weight: .medium, design: .monospaced))
                    .foregroundStyle(indicatorColor)
            }
        }
        .onAppear { isPulsing = quality != .disconnected }
        .onChange(of: quality) { _, newVal in isPulsing = newVal != .disconnected }
    }
}

#Preview {
    VStack(spacing: 16) {
        RFConnectionIndicator(quality: .excellent, latencyMs: 45)
        RFConnectionIndicator(quality: .fair, latencyMs: 320)
        RFConnectionIndicator(quality: .poor, latencyMs: 650)
        RFConnectionIndicator(quality: .disconnected, latencyMs: 0)
    }
    .padding()
    .background(Color.black)
}
