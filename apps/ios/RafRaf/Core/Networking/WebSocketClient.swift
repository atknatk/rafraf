import Foundation
import os

/// WebSocket baglanti durumlari.
enum WebSocketConnectionState: Sendable {
    case disconnected
    case connecting
    case connected
    case reconnecting
}

/// WebSocket istemcisi.
/// Native URLSession WebSocket API kullanir (3rd party kutuphane yok).
actor WebSocketClient {
    private var webSocketTask: URLSessionWebSocketTask?
    private let session: URLSession
    private let url: URL
    private let logger = Logger(
        subsystem: "com.rafraf",
        category: "WebSocketClient"
    )

    private(set) var state: WebSocketConnectionState = .disconnected

    init(url: URL = AppEnvironment.current.webSocketURL) {
        self.url = url
        self.session = URLSession(configuration: .default)
    }

    /// WebSocket baglantisini baslatir.
    func connect() async {
        guard state == .disconnected || state == .reconnecting else {
            logger.warning("Baglanti zaten aktif veya baglaniyor: \(String(describing: self.state))")
            return
        }

        state = .connecting
        logger.info("WebSocket baglantisi baslatiliyor: \(self.url.absoluteString)")

        webSocketTask = session.webSocketTask(with: url)
        webSocketTask?.resume()
        state = .connected

        logger.info("WebSocket baglantisi kuruldu")
    }

    /// WebSocket baglantisini kapatir.
    func disconnect() {
        webSocketTask?.cancel(with: .normalClosure, reason: nil)
        webSocketTask = nil
        state = .disconnected
        logger.info("WebSocket baglantisi kapatildi")
    }

    /// Mesaj gonderir.
    func send(_ message: String) async throws {
        guard let task = webSocketTask else {
            logger.error("WebSocket bagli degil, mesaj gonderilemedi")
            return
        }
        try await task.send(.string(message))
        logger.debug("Mesaj gonderildi: \(message.prefix(100))")
    }

    /// Mesaj dinler.
    func receive() async throws -> String {
        guard let task = webSocketTask else {
            throw WebSocketError.notConnected
        }

        let message = try await task.receive()

        switch message {
        case .string(let text):
            logger.debug("Mesaj alindi: \(text.prefix(100))")
            return text
        case .data(let data):
            guard let text = String(data: data, encoding: .utf8) else {
                throw WebSocketError.invalidData
            }
            return text
        @unknown default:
            throw WebSocketError.unknownMessageType
        }
    }
}

/// WebSocket hatalari.
enum WebSocketError: Error, Sendable {
    case notConnected
    case invalidData
    case unknownMessageType
    case connectionFailed(String)
}
