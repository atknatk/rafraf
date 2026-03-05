import SwiftUI

/// Baglanti kalite gostergesi — kucuk renkli nokta + gecikme.
/// Tiklandiginda kalite detayi gosteren popover acar.
struct RFConnectionIndicator: View {
    let quality: ConnectionQualityMonitor.Quality
    let latencyMs: Int

    @State private var isPulsing = false
    @State private var showPopover = false

    var indicatorColor: Color {
        switch quality {
        case .excellent, .good: return .green
        case .fair: return .yellow
        case .poor: return .red
        case .disconnected: return .gray
        }
    }

    private var qualityLabel: String {
        switch quality {
        case .excellent: return String(localized: "connection.quality.excellent")
        case .good: return String(localized: "connection.quality.good")
        case .fair: return String(localized: "connection.quality.fair")
        case .poor: return String(localized: "connection.quality.poor")
        case .disconnected: return String(localized: "connection.quality.disconnected")
        }
    }

    var body: some View {
        Button {
            showPopover.toggle()
        } label: {
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
        }
        .buttonStyle(.plain)
        .popover(isPresented: $showPopover, arrowEdge: .top) {
            connectionPopover
                .presentationCompactAdaptation(.popover)
        }
        .onAppear { isPulsing = quality != .disconnected }
        .onChange(of: quality) { _, newVal in isPulsing = newVal != .disconnected }
    }

    private var connectionPopover: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                Circle()
                    .fill(indicatorColor)
                    .frame(width: 8, height: 8)
                Text(qualityLabel)
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(.primary)
            }

            if latencyMs > 0 {
                HStack {
                    Text(String(localized: "connection.latency"))
                        .font(.system(size: 12))
                        .foregroundStyle(.secondary)
                    Spacer()
                    Text("\(latencyMs) ms")
                        .font(.system(size: 12, weight: .medium, design: .monospaced))
                        .foregroundStyle(indicatorColor)
                }
            }

            if quality == .disconnected {
                Text(String(localized: "connection.reconnecting"))
                    .font(.system(size: 11))
                    .foregroundStyle(.secondary)
            }
        }
        .padding(12)
        .frame(minWidth: 160)
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
