import Foundation
@testable import RafRaf

/// Test icin mock chat repository.
final class MockChatRepository: ChatRepositoryProtocol, @unchecked Sendable {
    var sendMessageResult: Result<ChatMessage, Error> = .success(
        ChatMessage(
            id: "sent-msg-1",
            content: "Test mesaji",
            sender: .user,
            timestamp: Date(),
            type: .text
        )
    )

    var loadHistoryResult: Result<ChatHistoryResult, Error> = .success(
        ChatHistoryResult(messages: [], hasMore: false, nextCursor: nil)
    )

    var sendMessageCallCount = 0
    var loadHistoryCallCount = 0
    var lastSentText: String?
    var lastSessionId: String?
    var lastCursor: String?
    var lastLimit: Int?

    func sendMessage(text: String, sessionId: String) async throws -> ChatMessage {
        sendMessageCallCount += 1
        lastSentText = text
        lastSessionId = sessionId
        return try sendMessageResult.get()
    }

    func loadHistory(
        sessionId: String,
        cursor: String?,
        limit: Int
    ) async throws -> ChatHistoryResult {
        loadHistoryCallCount += 1
        lastSessionId = sessionId
        lastCursor = cursor
        lastLimit = limit
        return try loadHistoryResult.get()
    }
}
