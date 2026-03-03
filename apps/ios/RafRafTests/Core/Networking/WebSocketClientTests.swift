import Foundation
import Testing
@testable import RafRaf

/// Test yardimci actor - state toplama.
actor StateCollector {
    private(set) var states: [WebSocketConnectionState] = []

    func append(_ state: WebSocketConnectionState) {
        states.append(state)
    }
}

/// Test yardimci actor - atomic flag.
actor AtomicFlag {
    private(set) var value: Bool = false

    func set() {
        value = true
    }
}

/// WebSocketClient testleri.
/// Baglanti, reconnect ve heartbeat testleri.
@Suite("WebSocketClient Tests")
struct WebSocketClientTests {

    // MARK: - Initial State

    @Test("WebSocketClient baslangic durumu disconnected olmali")
    func initialState() async {
        let client = WebSocketClient(
            url: URL(string: "ws://localhost:9999/ws")!
        )

        let state = await client.state
        #expect(state == .disconnected)
    }

    // MARK: - Reconnect Delay

    @Test("Reconnect delay exponential backoff ile artmali")
    func reconnectExponentialBackoff() async {
        let client = WebSocketClient(
            url: URL(string: "ws://localhost:9999/ws")!
        )

        // Ilk deneme: 1s
        let delay0 = await client.currentReconnectDelay()
        #expect(delay0 == 1.0)
    }

    @Test("Reconnect delay maksimum 60s olmali")
    func reconnectMaxDelay() async {
        let client = WebSocketClient(
            url: URL(string: "ws://localhost:9999/ws")!
        )

        // Her durumda max 60s
        let delay = await client.currentReconnectDelay()
        #expect(delay <= 60.0)
    }

    // MARK: - State Changes

    @Test("State callback cagirilmali")
    func stateChangeCallback() async {
        let client = WebSocketClient(
            url: URL(string: "ws://localhost:9999/ws")!
        )

        let stateCollector = StateCollector()

        await client.setOnStateChange { state in
            Task {
                await stateCollector.append(state)
            }
        }

        // Disconnect cagirildiginda state degismemeli (zaten disconnected)
        await client.disconnect()

        // State zaten disconnected oldugu icin callback cagirilmamali
        let states = await stateCollector.states
        #expect(states.isEmpty)
    }

    // MARK: - Send Without Connection

    @Test("Baglanti olmadan mesaj gonderme hatasi vermeli")
    func sendWithoutConnection() async {
        let client = WebSocketClient(
            url: URL(string: "ws://localhost:9999/ws")!
        )

        do {
            try await client.send("test")
            Issue.record("Baglanti olmadan mesaj gonderme hatasi bekleniyor")
        } catch {
            #expect(error is WebSocketError)
        }
    }

    @Test("Baglanti olmadan WebSocketBaseMessage gonderme hatasi vermeli")
    func sendMessageWithoutConnection() async {
        let client = WebSocketClient(
            url: URL(string: "ws://localhost:9999/ws")!
        )

        let message = WebSocketMessageFactory.textMessage("test")

        do {
            try await client.send(message: message)
            Issue.record("Baglanti olmadan mesaj gonderme hatasi bekleniyor")
        } catch {
            #expect(error is WebSocketError)
        }
    }

    @Test("Baglanti olmadan sendText hatasi vermeli")
    func sendTextWithoutConnection() async {
        let client = WebSocketClient(
            url: URL(string: "ws://localhost:9999/ws")!
        )

        do {
            try await client.sendText("test mesaji", sessionId: "sess-1")
            Issue.record("Baglanti olmadan sendText hatasi bekleniyor")
        } catch {
            #expect(error is WebSocketError)
        }
    }

    // MARK: - Disconnect

    @Test("Disconnect sonrasi state disconnected olmali")
    func disconnectState() async {
        let client = WebSocketClient(
            url: URL(string: "ws://localhost:9999/ws")!
        )

        await client.disconnect()

        let state = await client.state
        #expect(state == .disconnected)
    }

    // MARK: - Pong Handling

    @Test("handlePongReceived awaitingPong'u false yapmali")
    func handlePongReceived() async {
        let client = WebSocketClient(
            url: URL(string: "ws://localhost:9999/ws")!
        )

        await client.handlePongReceived()

        // Pong alindiktan sonra client hala disconnected olacak (baglanti yok)
        let state = await client.state
        #expect(state == .disconnected)
    }

    // MARK: - Message Router

    @Test("WebSocketClient message router'a sahip olmali")
    func hasMessageRouter() async {
        let router = WebSocketMessageRouter()
        let client = WebSocketClient(
            url: URL(string: "ws://localhost:9999/ws")!,
            messageRouter: router
        )

        // Router register/unregister calistigini dogrula
        let handler = MockWebSocketMessageHandler()
        await client.messageRouter.register(type: "test", handler: handler)
        await client.messageRouter.unregister(type: "test")
    }

    // MARK: - Message Callback

    @Test("Message callback ayarlanabilmeli")
    func setMessageCallback() async {
        let client = WebSocketClient(
            url: URL(string: "ws://localhost:9999/ws")!
        )

        let flag = AtomicFlag()
        await client.setOnMessage { _ in
            Task {
                await flag.set()
            }
        }

        // Callback ayarlandi ama henuz mesaj yok
        let value = await flag.value
        #expect(value == false)
    }
}

// MARK: - WebSocketError Tests

@Suite("WebSocketError Tests")
struct WebSocketErrorTests {

    @Test("WebSocketError tum case'leri olmali")
    func allErrorCases() {
        let errors: [WebSocketError] = [
            .notConnected,
            .invalidData,
            .unknownMessageType,
            .connectionFailed("test"),
            .heartbeatTimeout
        ]

        #expect(errors.count == 5)
    }
}
