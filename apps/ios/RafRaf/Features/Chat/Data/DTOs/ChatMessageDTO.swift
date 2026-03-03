import Foundation

/// Chat mesaji API response DTO.
/// `shared/api-contracts/ws/chat-messages.json` kontratina uygun.
struct ChatMessageDTO: Codable, Sendable {
    let messageId: String
    let text: String
    let sender: String
    let type: String
    let timestamp: String
    let attachments: [ChatAttachmentDTO]?
}

/// Chat gecmisi response DTO.
struct ChatHistoryResponseDTO: Codable, Sendable {
    let messages: [ChatMessageDTO]
    let hasMore: Bool
    let nextCursor: String?
}

/// Chat stream parca DTO.
struct ChatStreamDTO: Codable, Sendable {
    let messageId: String
    let delta: String
    let index: Int
}

/// Chat stream bitis DTO.
struct ChatStreamEndDTO: Codable, Sendable {
    let messageId: String
    let fullText: String
    let type: String
}

/// Chat typing indicator DTO.
struct ChatTypingDTO: Codable, Sendable {
    let isTyping: Bool
}
