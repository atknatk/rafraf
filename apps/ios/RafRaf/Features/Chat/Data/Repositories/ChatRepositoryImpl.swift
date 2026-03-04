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

        // Backend "text" tipi bekler, content duz metin olmali
        try await webSocketClient.sendText(text, sessionId: sessionId)
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
        // Yeni session — gecmis yok, bos doner
        // Ileride REST endpoint (/api/v1/conversations/{sessionId}/messages) entegre edilecek
        logger.info("Mesaj gecmisi istendi - session: \(sessionId), cursor: \(cursor ?? "nil")")
        return ChatHistoryResult(messages: [], hasMore: false, nextCursor: nil)
    }
}

/// Chat repository hatalari.
enum ChatRepositoryError: Error, Sendable {
    case encodingFailed
    case decodingFailed
    case connectionError
}
