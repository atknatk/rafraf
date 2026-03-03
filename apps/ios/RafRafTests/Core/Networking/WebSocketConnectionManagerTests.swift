import Foundation
import Testing
@testable import RafRaf

/// WebSocketConnectionManager testleri.
@Suite("WebSocketConnectionManager Tests")
struct WebSocketConnectionManagerTests {

    // MARK: - Initial State

    @Test("ConnectionManager baslangic durumu disconnected olmali")
    @MainActor
    func initialState() {
        let client = WebSocketClient(url: URL(string: "ws://localhost:9999/ws")!)
        let manager = WebSocketConnectionManager(webSocketClient: client)

        #expect(manager.connectionState == .disconnected)
        #expect(manager.isConnected == false)
        #expect(manager.lastError == nil)
        #expect(manager.connectedSince == nil)
        #expect(manager.lastMessageReceivedAt == nil)
    }

    // MARK: - Status Text

    @Test("statusText disconnected durumunda dogru localized string donmeli")
    @MainActor
    func statusTextDisconnected() {
        let client = WebSocketClient(url: URL(string: "ws://localhost:9999/ws")!)
        let manager = WebSocketConnectionManager(webSocketClient: client)

        // connectionState .disconnected oldugu icin statusText bos olmamali
        #expect(!manager.statusText.isEmpty)
    }

    // MARK: - isConnected

    @Test("isConnected disconnected durumunda false olmali")
    @MainActor
    func isConnectedFalse() {
        let client = WebSocketClient(url: URL(string: "ws://localhost:9999/ws")!)
        let manager = WebSocketConnectionManager(webSocketClient: client)

        #expect(manager.isConnected == false)
    }

    // MARK: - Send Without Connection

    @Test("sendText baglanti olmadan hata vermeli")
    @MainActor
    func sendTextWithoutConnection() async {
        let client = WebSocketClient(url: URL(string: "ws://localhost:9999/ws")!)
        let manager = WebSocketConnectionManager(webSocketClient: client)

        do {
            try await manager.sendText("test mesaji")
            Issue.record("Baglanti olmadan sendText hatasi bekleniyor")
        } catch {
            #expect(error is WebSocketError)
        }
    }

    // MARK: - Handler Registration

    @Test("Handler kaydedilip kaldirilabilmeli")
    @MainActor
    func registerAndUnregisterHandler() async {
        let client = WebSocketClient(url: URL(string: "ws://localhost:9999/ws")!)
        let manager = WebSocketConnectionManager(webSocketClient: client)
        let handler = MockWebSocketMessageHandler()

        await manager.registerHandler(type: "text", handler: handler)
        await manager.unregisterHandler(type: "text")
    }

    // MARK: - Disconnect

    @Test("disconnect sonrasi connectedSince nil olmali")
    @MainActor
    func disconnectClearsConnectedSince() async {
        let client = WebSocketClient(url: URL(string: "ws://localhost:9999/ws")!)
        let manager = WebSocketConnectionManager(webSocketClient: client)

        await manager.disconnect()

        #expect(manager.connectedSince == nil)
        #expect(manager.connectionState == .disconnected)
    }

    // MARK: - Connect

    @Test("connect lastError'u temizlemeli")
    @MainActor
    func connectClearsLastError() async {
        let client = WebSocketClient(url: URL(string: "ws://localhost:9999/ws")!)
        let manager = WebSocketConnectionManager(webSocketClient: client)

        // connect cagrildiginda lastError nil olacak
        await manager.connect()

        #expect(manager.lastError == nil)
    }
}
