import Foundation
import os

/// Chat repository implementasyonu.
/// WebSocket uzerinden mesaj gonderme ve gecmis yukleme islemlerini gerceklestirir.
final class ChatRepositoryImpl: ChatRepositoryProtocol, @unchecked Sendable {
    private let webSocketClient: WebSocketClient
    private let logger = AppLogger.logger(for: "ChatRepository")

    init(webSocketClient: WebSocketClient) {
        self.webSocketClient = webSocketClient
    }

    func sendMessage(text: String, sessionId: String) async throws -> ChatMessage {
        let messageId = UUID().uuidString

        let payload: [String: String] = [
            "text": text,
            "session_id": sessionId
        ]

        let payloadData = try JSONSerialization.data(withJSONObject: payload)
        guard let payloadString = String(data: payloadData, encoding: .utf8) else {
            throw ChatRepositoryError.encodingFailed
        }

        let wsMessage = WebSocketBaseMessage(
            id: messageId,
            type: "chat.send",
            content: .text(payloadString),
            metadata: WebSocketMessageMetadata(
                sessionId: sessionId,
                direction: WebSocketMessageDirection.clientToServer.rawValue
            )
        )

        try await webSocketClient.send(message: wsMessage)
        logger.info("Mesaj gonderildi: \(messageId)")

        return ChatMessage(
            id: messageId,
            content: text,
            sender: .user,
            timestamp: Date(),
            type: .text
        )
    }

    func loadHistory(
        sessionId: String,
        cursor: String?,
        limit: Int
    ) async throws -> ChatHistoryResult {
        var payload: [String: Any] = [
            "session_id": sessionId,
            "limit": limit
        ]

        if let cursor {
            payload["cursor"] = cursor
        }

        let payloadData = try JSONSerialization.data(withJSONObject: payload)
        guard let payloadString = String(data: payloadData, encoding: .utf8) else {
            throw ChatRepositoryError.encodingFailed
        }

        let wsMessage = WebSocketBaseMessage(
            id: UUID().uuidString,
            type: "chat.history",
            content: .text(payloadString),
            metadata: WebSocketMessageMetadata(
                sessionId: sessionId,
                direction: WebSocketMessageDirection.clientToServer.rawValue
            )
        )

        try await webSocketClient.send(message: wsMessage)
        logger.info("Mesaj gecmisi istendi - session: \(sessionId), cursor: \(cursor ?? "nil")")

        // Gecmis response WebSocket message handler tarafindan ChatViewModel'e iletilir
        // Bu metod sadece istegi gonderir, response asenkron gelir
        return ChatHistoryResult(messages: [], hasMore: false, nextCursor: nil)
    }
}

/// Chat repository hatalari.
enum ChatRepositoryError: Error, Sendable {
    case encodingFailed
    case decodingFailed
    case connectionError
}
