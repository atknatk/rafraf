import Foundation
import os

/// WebSocket baglanti durumlari.
enum WebSocketConnectionState: Sendable, Equatable {
    case disconnected
    case connecting
    case connected
    case reconnecting
}

/// WebSocket istemcisi.
/// Native URLSession WebSocket API kullanir (3rd party kutuphane yok).
/// Auto-reconnect, heartbeat, mesaj encode/decode ozellikleri icerir.
actor WebSocketClient {
    private var webSocketTask: URLSessionWebSocketTask?
    private let session: URLSession
    private let url: URL
    private let logger = Logger(
        subsystem: "com.rafraf",
        category: "WebSocketClient"
    )

    private(set) var state: WebSocketConnectionState = .disconnected

    /// Reconnect ayarlari
    private var reconnectAttempt: Int = 0
    private let maxReconnectDelay: TimeInterval = 60.0
    private let baseReconnectDelay: TimeInterval = 1.0
    private var shouldReconnect: Bool = true
    private var reconnectTask: Task<Void, Never>?

    /// Heartbeat ayarlari
    private let heartbeatInterval: TimeInterval = 30.0
    private let heartbeatTimeout: TimeInterval = 10.0
    private var heartbeatTask: Task<Void, Never>?
    private var lastPongReceived: Date = Date()
    private var awaitingPong: Bool = false

    /// Mesaj dinleme
    private var receiveTask: Task<Void, Never>?

    /// Mesaj yonlendirici
    let messageRouter: WebSocketMessageRouter

    /// State degisiklik callback'i
    private var onStateChange: (@Sendable (WebSocketConnectionState) -> Void)?

    /// Gelen mesaj callback'i
    private var onMessage: (@Sendable (String) -> Void)?

    init(
        url: URL = AppEnvironment.current.webSocketURL,
        messageRouter: WebSocketMessageRouter = WebSocketMessageRouter()
    ) {
        self.url = url
        self.session = URLSession(configuration: .default)
        self.messageRouter = messageRouter
    }

    // MARK: - Public API

    /// State degisiklik callback'ini ayarlar.
    func setOnStateChange(_ callback: @escaping @Sendable (WebSocketConnectionState) -> Void) {
        self.onStateChange = callback
    }

    /// Gelen mesaj callback'ini ayarlar.
    func setOnMessage(_ callback: @escaping @Sendable (String) -> Void) {
        self.onMessage = callback
    }

    /// WebSocket baglantisini baslatir.
    func connect() async {
        guard state == .disconnected || state == .reconnecting else {
            logger.warning("Baglanti zaten aktif veya baglaniyor: \(String(describing: self.state))")
            return
        }

        shouldReconnect = true
        updateState(.connecting)
        logger.info("WebSocket baglantisi baslatiliyor: \(self.url.absoluteString)")

        webSocketTask = session.webSocketTask(with: url)
        webSocketTask?.resume()

        reconnectAttempt = 0
        updateState(.connected)
        lastPongReceived = Date()

        logger.info("WebSocket baglantisi kuruldu")

        startReceiving()
        startHeartbeat()
    }

    /// WebSocket baglantisini kapatir. Auto-reconnect devre disi kalir.
    func disconnect() {
        shouldReconnect = false
        stopHeartbeat()
        stopReceiving()
        cancelReconnect()

        webSocketTask?.cancel(with: .normalClosure, reason: nil)
        webSocketTask = nil
        updateState(.disconnected)
        logger.info("WebSocket baglantisi kapatildi")
    }

    /// Mesaj gonderir (JSON encode edilmis string).
    func send(_ message: String) async throws {
        guard let task = webSocketTask, state == .connected else {
            logger.error("WebSocket bagli degil, mesaj gonderilemedi")
            throw WebSocketError.notConnected
        }
        try await task.send(.string(message))
        logger.debug("Mesaj gonderildi: \(message.prefix(100))")
    }

    /// WebSocketBaseMessage gonderir (otomatik JSON encode).
    func send(message: WebSocketBaseMessage) async throws {
        let jsonString = try await messageRouter.encode(message)
        try await send(jsonString)
    }

    /// Metin mesaji gonderir.
    func sendText(
        _ text: String,
        sessionId: String? = nil,
        projectId: String? = nil
    ) async throws {
        let message = WebSocketMessageFactory.textMessage(
            text,
            sessionId: sessionId,
            projectId: projectId
        )
        try await send(message: message)
    }

    // MARK: - Reconnect

    /// Mevcut reconnect gecikmesini hesaplar (exponential backoff).
    func currentReconnectDelay() -> TimeInterval {
        let delay = baseReconnectDelay * pow(2.0, Double(reconnectAttempt))
        return min(delay, maxReconnectDelay)
    }

    private func scheduleReconnect() {
        guard shouldReconnect else {
            logger.info("Auto-reconnect devre disi, yeniden baglanti yapilmayacak")
            return
        }

        cancelReconnect()
        updateState(.reconnecting)

        let delay = currentReconnectDelay()
        reconnectAttempt += 1

        logger.info("Yeniden baglanti denemesi \(self.reconnectAttempt), bekleme: \(delay)s")

        reconnectTask = Task { [weak self] in
            do {
                try await Task.sleep(for: .seconds(delay))
                guard let self = self, !Task.isCancelled else { return }
                await self.connect()
            } catch {
                // Task iptal edildi
            }
        }
    }

    private func cancelReconnect() {
        reconnectTask?.cancel()
        reconnectTask = nil
    }

    // MARK: - Heartbeat

    private func startHeartbeat() {
        stopHeartbeat()

        heartbeatTask = Task { [weak self] in
            while !Task.isCancelled {
                do {
                    try await Task.sleep(for: .seconds(self?.heartbeatInterval ?? 30.0))
                    guard let self = self, !Task.isCancelled else { return }

                    let currentState = await self.getState()
                    guard currentState == .connected else { return }

                    // Pong timeout kontrolu
                    if await self.isAwaitingPong() {
                        let timeSincePong = await self.timeSinceLastPong()
                        if timeSincePong > (self.heartbeatTimeout + self.heartbeatInterval) {
                            await self.handleHeartbeatTimeout()
                            return
                        }
                    }

                    await self.sendPing()
                } catch {
                    return
                }
            }
        }
    }

    private func stopHeartbeat() {
        heartbeatTask?.cancel()
        heartbeatTask = nil
        awaitingPong = false
    }

    private func sendPing() async {
        let pingMessage = WebSocketMessageFactory.pingMessage()
        do {
            try await send(message: pingMessage)
            awaitingPong = true
            logger.debug("Ping gonderildi")
        } catch {
            logger.warning("Ping gonderilemedi: \(error.localizedDescription)")
        }
    }

    func handlePongReceived() {
        lastPongReceived = Date()
        awaitingPong = false
        logger.debug("Pong alindi")
    }

    private func handleHeartbeatTimeout() {
        logger.warning("Heartbeat timeout - baglanti kopmus kabul ediliyor")
        webSocketTask?.cancel(with: .abnormalClosure, reason: nil)
        webSocketTask = nil
        stopReceiving()
        stopHeartbeat()
        scheduleReconnect()
    }

    private func getState() -> WebSocketConnectionState {
        state
    }

    private func isAwaitingPong() -> Bool {
        awaitingPong
    }

    private func timeSinceLastPong() -> TimeInterval {
        Date().timeIntervalSince(lastPongReceived)
    }

    // MARK: - Receive Loop

    private func startReceiving() {
        stopReceiving()

        receiveTask = Task { [weak self] in
            while !Task.isCancelled {
                guard let self = self else { return }

                do {
                    let text = try await self.receiveNext()
                    await self.handleReceivedMessage(text)
                } catch {
                    if !Task.isCancelled {
                        await self.handleReceiveError(error)
                    }
                    return
                }
            }
        }
    }

    private func stopReceiving() {
        receiveTask?.cancel()
        receiveTask = nil
    }

    private func receiveNext() async throws -> String {
        guard let task = webSocketTask else {
            throw WebSocketError.notConnected
        }

        let message = try await task.receive()

        switch message {
        case .string(let text):
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

    private func handleReceivedMessage(_ text: String) async {
        logger.debug("Mesaj alindi: \(text.prefix(100))")

        onMessage?(text)

        // Router ile mesaji isle
        do {
            let message = try await messageRouter.route(text)

            // Pong mesajini ozel isle
            if message.type == WebSocketMessageType.pong.rawValue {
                handlePongReceived()
            }

            // Ping mesajina otomatik pong cevabi
            if message.type == WebSocketMessageType.ping.rawValue {
                let pong = WebSocketMessageFactory.pongMessage()
                try? await send(message: pong)
            }
        } catch {
            logger.warning("Mesaj routing hatasi: \(error.localizedDescription)")
        }
    }

    private func handleReceiveError(_ error: Error) {
        logger.error("Mesaj alma hatasi: \(error.localizedDescription)")
        webSocketTask = nil
        stopHeartbeat()
        scheduleReconnect()
    }

    // MARK: - State Management

    private func updateState(_ newState: WebSocketConnectionState) {
        let oldState = state
        state = newState

        if oldState != newState {
            logger.info("State degisimi: \(String(describing: oldState)) -> \(String(describing: newState))")
            onStateChange?(newState)
        }
    }
}

/// WebSocket hatalari.
enum WebSocketError: Error, Sendable {
    case notConnected
    case invalidData
    case unknownMessageType
    case connectionFailed(String)
    case heartbeatTimeout
}
