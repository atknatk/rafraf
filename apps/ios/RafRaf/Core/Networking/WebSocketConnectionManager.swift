import Foundation
import os
import Observation
import UIKit

/// Observer token depolama.
/// deinit'ten erisilebilmesi icin nonisolated(unsafe) kullanilir.
private final class ObserverStorage: @unchecked Sendable {
    var observers: [NSObjectProtocol] = []

    func removeAll() {
        for observer in observers {
            NotificationCenter.default.removeObserver(observer)
        }
        observers.removeAll()
    }
}

/// WebSocket baglanti yoneticisi.
/// @Observable ile UI'a reaktif state bildirimi saglar.
/// Background/foreground transition handling icerir.
@Observable
@MainActor
final class WebSocketConnectionManager {
    /// Mevcut baglanti durumu.
    private(set) var connectionState: WebSocketConnectionState = .disconnected

    /// Son hata mesaji.
    private(set) var lastError: String?

    /// Baglanti suresi (saniye).
    private(set) var connectedSince: Date?

    /// Son alinan mesaj zamani.
    private(set) var lastMessageReceivedAt: Date?

    /// Reconnect callback — app foreground'a donunce veya WebSocket reconnect sonrasi cagirilir.
    var onReconnect: (() async -> Void)?

    private let webSocketClient: WebSocketClient
    private let logger = Logger(
        subsystem: "com.rafraf",
        category: "WebSocketConnectionManager"
    )

    /// Background/foreground observer'lar
    private let observerStorage = ObserverStorage()

    /// Bagli mi?
    var isConnected: Bool {
        connectionState == .connected
    }

    /// Durum aciklamasi (localized).
    var statusText: String {
        switch connectionState {
        case .disconnected:
            return String(localized: "websocket.status.disconnected")
        case .connecting:
            return String(localized: "websocket.status.connecting")
        case .connected:
            return String(localized: "websocket.status.connected")
        case .reconnecting:
            return String(localized: "websocket.status.reconnecting")
        }
    }

    init(webSocketClient: WebSocketClient) {
        self.webSocketClient = webSocketClient
        setupStateCallback()
        setupMessageCallback()
        setupAppLifecycleObservers()
    }

    deinit {
        observerStorage.removeAll()
    }

    // MARK: - Public API

    /// Baglanti baslatir.
    func connect() async {
        lastError = nil
        await webSocketClient.connect()
    }

    /// Baglantiyi kapatir.
    func disconnect() async {
        await webSocketClient.disconnect()
        connectedSince = nil
    }

    /// Mesaj gonderir.
    func sendText(
        _ text: String,
        sessionId: String? = nil,
        projectId: String? = nil
    ) async throws {
        try await webSocketClient.sendText(
            text,
            sessionId: sessionId,
            projectId: projectId
        )
    }

    /// Yapilandirilmis WebSocket mesaji gonderir.
    func sendMessage(_ message: WebSocketBaseMessage) async throws {
        try await webSocketClient.send(message: message)
    }

    /// Mesaj handler kaydeder.
    func registerHandler(
        type: String,
        handler: WebSocketMessageHandler
    ) async {
        await webSocketClient.messageRouter.register(type: type, handler: handler)
    }

    /// Mesaj handler kaldirir.
    func unregisterHandler(type: String) async {
        await webSocketClient.messageRouter.unregister(type: type)
    }

    // MARK: - Private Setup

    private func setupStateCallback() {
        Task {
            await webSocketClient.setOnStateChange { [weak self] newState in
                Task { @MainActor [weak self] in
                    guard let self else { return }
                    self.connectionState = newState

                    if newState == .connected {
                        self.connectedSince = Date()
                        self.lastError = nil
                        // Reconnect sonrasi kacirilmis mesajlari fetch et
                        if let onReconnect = self.onReconnect {
                            Task { await onReconnect() }
                        }
                    } else if newState == .disconnected {
                        self.connectedSince = nil
                    }
                }
            }
        }
    }

    private func setupMessageCallback() {
        Task {
            await webSocketClient.setOnMessage { [weak self] _ in
                Task { @MainActor [weak self] in
                    self?.lastMessageReceivedAt = Date()
                }
            }
        }
    }

    // MARK: - App Lifecycle

    private func setupAppLifecycleObservers() {
        #if os(iOS)
        let backgroundObserver = NotificationCenter.default.addObserver(
            forName: UIApplication.didEnterBackgroundNotification,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            guard let self else { return }
            Task { @MainActor in
                self.logger.info("Uygulama background'a gecti, baglanti kapatiliyor")
                await self.disconnect()
            }
        }

        let foregroundObserver = NotificationCenter.default.addObserver(
            forName: UIApplication.willEnterForegroundNotification,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            guard let self else { return }
            Task { @MainActor in
                self.logger.info("Uygulama foreground'a dondu, baglanti baslatiliyor")
                await self.connect()
            }
        }

        observerStorage.observers = [backgroundObserver, foregroundObserver]
        #endif
    }
}
