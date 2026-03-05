import Foundation
import os

/// WebSocket baglanti kalite monitoru.
/// Ping/pong suresini olcer ve kalite seviyesini hesaplar.
@Observable
@MainActor
final class ConnectionQualityMonitor {

    enum Quality: Sendable {
        case excellent    // < 100ms
        case good         // 100-250ms
        case fair         // 250-500ms
        case poor         // > 500ms
        case disconnected

        var color: String {  // color name for use in SwiftUI
            switch self {
            case .excellent: return "green"
            case .good: return "green"
            case .fair: return "yellow"
            case .poor: return "red"
            case .disconnected: return "gray"
            }
        }

        var label: String {
            switch self {
            case .excellent: return String(localized: "connection.quality.excellent")
            case .good: return String(localized: "connection.quality.good")
            case .fair: return String(localized: "connection.quality.fair")
            case .poor: return String(localized: "connection.quality.poor")
            case .disconnected: return String(localized: "connection.quality.disconnected")
            }
        }
    }

    private(set) var quality: Quality = .disconnected
    private(set) var latencyMs: Int = 0
    private(set) var isConnected: Bool = false

    private var pingTime: Date?
    private var pingTimer: Timer?
    private let logger = Logger(subsystem: "com.rafraf", category: "ConnectionQuality")

    func connectionEstablished() {
        isConnected = true
        quality = .good
        schedulePing()
    }

    func connectionLost() {
        isConnected = false
        quality = .disconnected
        latencyMs = 0
        pingTimer?.invalidate()
        pingTimer = nil
    }

    func recordPingSent() {
        pingTime = Date()
    }

    func recordPongReceived() {
        guard let sent = pingTime else { return }
        let elapsed = Date().timeIntervalSince(sent) * 1000
        latencyMs = Int(elapsed)
        pingTime = nil
        quality = qualityFromLatency(latencyMs)
        logger.debug("Ping latency: \(self.latencyMs)ms, quality: \(self.quality.label)")
    }

    private func qualityFromLatency(_ ms: Int) -> Quality {
        switch ms {
        case 0..<100: return .excellent
        case 100..<250: return .good
        case 250..<500: return .fair
        default: return .poor
        }
    }

    private func schedulePing() {
        pingTimer?.invalidate()
        pingTimer = Timer.scheduledTimer(withTimeInterval: 10.0, repeats: true) { [weak self] _ in
            Task { @MainActor in
                self?.logger.debug("Ping timer fired")
                // Ping is sent by WebSocketClient heartbeat; recordPingSent() called at send time
            }
        }
    }
}
