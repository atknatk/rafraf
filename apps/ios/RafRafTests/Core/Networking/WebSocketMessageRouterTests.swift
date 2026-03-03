import Foundation
import Testing
@testable import RafRaf

/// Mock WebSocket mesaj handler.
final class MockWebSocketMessageHandler: WebSocketMessageHandler, @unchecked Sendable {
    private(set) var receivedMessages: [WebSocketBaseMessage] = []
    private(set) var handleCallCount: Int = 0

    func handle(_ message: WebSocketBaseMessage) async {
        receivedMessages.append(message)
        handleCallCount += 1
    }
}

/// WebSocketMessageRouter testleri.
@Suite("WebSocketMessageRouter Tests")
struct WebSocketMessageRouterTests {

    // MARK: - Handler Registration

    @Test("Handler kaydedilip mesaj yonlendirilmeli")
    func registerAndRoute() async throws {
        let router = WebSocketMessageRouter()
        let handler = MockWebSocketMessageHandler()

        await router.register(type: "text", handler: handler)

        let json = """
        {"id": "msg-1", "type": "text", "content": "Merhaba"}
        """

        try await router.route(json)

        #expect(handler.handleCallCount == 1)
        #expect(handler.receivedMessages.first?.type == "text")
    }

    @Test("Handler kaldirildiginda mesaj yonlendirilmemeli")
    func unregisterHandler() async throws {
        let router = WebSocketMessageRouter()
        let handler = MockWebSocketMessageHandler()

        await router.register(type: "text", handler: handler)
        await router.unregister(type: "text")

        let json = """
        {"id": "msg-1", "type": "text", "content": "Merhaba"}
        """

        // Handler kaldirildi, mesaj yonlendirilmemeli ama decode edilmeli
        let message = try await router.route(json)
        #expect(message.type == "text")
        #expect(handler.handleCallCount == 0)
    }

    @Test("Birden fazla handler farkli tiplere kaydedilebilmeli")
    func multipleHandlers() async throws {
        let router = WebSocketMessageRouter()
        let textHandler = MockWebSocketMessageHandler()
        let errorHandler = MockWebSocketMessageHandler()

        await router.register(type: "text", handler: textHandler)
        await router.register(type: "error", handler: errorHandler)

        let textJson = """
        {"id": "msg-1", "type": "text", "content": "Merhaba"}
        """

        let errorJson = """
        {"id": "msg-2", "type": "error", "content": {"error_code": "ERR", "message": "Hata", "recoverable": false}}
        """

        try await router.route(textJson)
        try await router.route(errorJson)

        #expect(textHandler.handleCallCount == 1)
        #expect(errorHandler.handleCallCount == 1)
    }

    // MARK: - Routing

    @Test("Bilinmeyen mesaj tipi icin handler yoksa hata vermemeli")
    func unknownMessageType() async throws {
        let router = WebSocketMessageRouter()

        let json = """
        {"id": "msg-1", "type": "unknown_type", "content": "test"}
        """

        // Hata vermeden decode etmeli
        let message = try await router.route(json)
        #expect(message.type == "unknown_type")
    }

    @Test("Gecersiz JSON icin hata vermeli")
    func invalidJson() async {
        let router = WebSocketMessageRouter()
        let invalidJson = "{ invalid json"

        do {
            try await router.route(invalidJson)
            Issue.record("Gecersiz JSON icin hata bekleniyor")
        } catch {
            // Beklenen davranis
            #expect(error is WebSocketMessageRouterError)
        }
    }

    @Test("Bos string icin hata vermeli")
    func emptyString() async {
        let router = WebSocketMessageRouter()

        do {
            try await router.route("")
            Issue.record("Bos string icin hata bekleniyor")
        } catch {
            #expect(error is WebSocketMessageRouterError)
        }
    }

    // MARK: - Encode

    @Test("Mesaj dogru JSON string'e encode edilmeli")
    func encodeMessage() async throws {
        let router = WebSocketMessageRouter()
        let message = WebSocketBaseMessage(
            id: "enc-1",
            type: "text",
            content: .text("Hello")
        )

        let jsonString = try await router.encode(message)

        #expect(jsonString.contains("enc-1"))
        #expect(jsonString.contains("text"))
        #expect(jsonString.contains("Hello"))
    }

    // MARK: - Route Return Value

    @Test("Route decode edilen mesaji donmeli")
    func routeReturnsMessage() async throws {
        let router = WebSocketMessageRouter()

        let json = """
        {"id": "ret-1", "type": "progress", "content": {"task": "Analiz", "step": 1, "total_steps": 5, "percentage": 20}}
        """

        let message = try await router.route(json)

        #expect(message.id == "ret-1")
        #expect(message.type == "progress")

        if case .progress(let progress) = message.content {
            #expect(progress.task == "Analiz")
            #expect(progress.step == 1)
            #expect(progress.totalSteps == 5)
            #expect(progress.percentage == 20)
        } else {
            Issue.record("Content progress olmali")
        }
    }
}
