import Foundation
import os

// MARK: - Response DTOs (private to data layer)

private struct ConversationHistoryDTO: Decodable, Sendable {
    let messages: [MessageResponseDTO]
    let hasMore: Bool
    let nextCursor: String?
}

private struct MessageResponseDTO: Decodable, Sendable {
    let id: String
    let role: String
    let content: String
    let createdAt: String
    let rating: String?
}

private struct MessageRatingRequestDTO: Encodable, Sendable {
    let rating: String
}

/// Chat repository implementasyonu.
/// WebSocket uzerinden mesaj gonderme, REST uzerinden gecmis yukleme.
final class ChatRepositoryImpl: ChatRepositoryProtocol, @unchecked Sendable {
    private let webSocketClient: WebSocketClient
    private let networkClient: NetworkClient
    private let logger = AppLogger.logger(for: "ChatRepository")

    init(webSocketClient: WebSocketClient, networkClient: NetworkClient) {
        self.webSocketClient = webSocketClient
        self.networkClient = networkClient
    }

    func sendMessage(text: String, sessionId: String, projectId: String? = nil, agentId: String? = nil) async throws -> ChatMessage {
        let messageId = UUID().uuidString

        try await webSocketClient.sendText(
            text,
            sessionId: sessionId,
            projectId: projectId,
            agentId: agentId
        )
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
        projectId: String? = nil,
        cursor: String?,
        limit: Int
    ) async throws -> ChatHistoryResult {
        var queryItems: [URLQueryItem] = [
            URLQueryItem(name: "limit", value: "\(limit)")
        ]
        // project_id varsa onu kullan — session_id iOS UUID'si, backend UUID'si ile eşleşmez
        if let projectId {
            queryItems.append(URLQueryItem(name: "project_id", value: projectId))
        } else {
            queryItems.append(URLQueryItem(name: "session_id", value: sessionId))
        }
        if let cursor {
            queryItems.append(URLQueryItem(name: "cursor", value: cursor))
        }

        let dto: ConversationHistoryDTO = try await networkClient.get(
            path: "/conversations/history",
            queryItems: queryItems
        )

        let messages = dto.messages.compactMap { msg -> ChatMessage? in
            let sender: MessageSender = msg.role == "user" ? .user : .assistant
            let rating: MessageRating? = msg.rating.flatMap { MessageRating(rawValue: $0) }
            return ChatMessage(
                id: msg.id,
                content: msg.content,
                sender: sender,
                timestamp: ISO8601DateFormatter().date(from: msg.createdAt) ?? Date(),
                type: .text,
                rating: rating
            )
        }

        logger.info("Mesaj gecmisi yuklendi - session: \(sessionId), count: \(messages.count)")
        return ChatHistoryResult(messages: messages, hasMore: dto.hasMore, nextCursor: dto.nextCursor)
    }

    func rateMessage(id: String, rating: MessageRating) async throws {
        let body = MessageRatingRequestDTO(rating: rating.rawValue)
        let _: MessageResponseDTO = try await networkClient.patch(
            path: "/conversations/\(id)/rating",
            body: body
        )
        logger.info("Mesaj degerlendirmesi gonderildi: \(id) — \(rating.rawValue)")
    }

    func fetchMissedMessages(
        since: String,
        sessionId: String?,
        projectId: String?
    ) async throws -> [ChatMessage] {
        var queryItems: [URLQueryItem] = [
            URLQueryItem(name: "since", value: since)
        ]
        if let sessionId {
            queryItems.append(URLQueryItem(name: "session_id", value: sessionId))
        }
        if let projectId {
            queryItems.append(URLQueryItem(name: "project_id", value: projectId))
        }

        let dto: ConversationHistoryDTO = try await networkClient.get(
            path: "/conversations/missed",
            queryItems: queryItems
        )

        let messages = dto.messages.compactMap { msg -> ChatMessage? in
            let sender: MessageSender = msg.role == "user" ? .user : .assistant
            return ChatMessage(
                id: msg.id,
                content: msg.content,
                sender: sender,
                timestamp: ISO8601DateFormatter().date(from: msg.createdAt) ?? Date(),
                type: .text
            )
        }

        logger.info("Kacirilmis mesajlar yuklendi: \(messages.count)")
        return messages
    }

    func loadRecent(limit: Int) async throws -> [ChatMessage] {
        let clamped = max(1, min(limit, 20))
        let queryItems: [URLQueryItem] = [
            URLQueryItem(name: "limit", value: "\(clamped)")
        ]

        let dto: ConversationHistoryDTO = try await networkClient.get(
            path: "/conversations/recent",
            queryItems: queryItems
        )

        let messages = dto.messages.compactMap { msg -> ChatMessage? in
            let sender: MessageSender = msg.role == "user" ? .user : .assistant
            let rating: MessageRating? = msg.rating.flatMap { MessageRating(rawValue: $0) }
            return ChatMessage(
                id: msg.id,
                content: msg.content,
                sender: sender,
                timestamp: ISO8601DateFormatter().date(from: msg.createdAt) ?? Date(),
                type: .text,
                rating: rating
            )
        }

        logger.info("Son mesajlar yuklendi: \(messages.count)")
        return messages
    }
}

/// Chat repository hatalari.
enum ChatRepositoryError: Error, Sendable {
    case encodingFailed
    case decodingFailed
    case connectionError
}
