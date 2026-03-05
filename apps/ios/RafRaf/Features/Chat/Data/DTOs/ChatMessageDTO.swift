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

/// Konusma mesaj search response DTO.
/// GET /api/v1/conversations/search endpoint'i icin.
struct MessageDTO: Codable, Sendable {
    let id: String
    let content: String
    let role: String
    let createdAt: String?
    let modelUsed: String?
    let tokensUsed: Int?
}

/// Code diff satiri DTO.
struct CodeDiffLineDTO: Codable, Sendable {
    let type: String  // "added", "removed", "context"
    let content: String
    let lineNumberOld: Int?
    let lineNumberNew: Int?
}

/// Dosya diff DTO.
struct CodeDiffFileDTO: Codable, Sendable {
    let filePath: String
    let isNewFile: Bool?
    let isDeleted: Bool?
    let additions: Int
    let deletions: Int
    let lines: [CodeDiffLineDTO]
}

/// Code diff mesaj payload DTO.
struct CodeDiffPayloadDTO: Codable, Sendable {
    let projectPath: String
    let totalAdditions: Int
    let totalDeletions: Int
    let filesChanged: Int
    let files: [CodeDiffFileDTO]
}
