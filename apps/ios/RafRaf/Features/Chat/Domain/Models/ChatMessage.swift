import Foundation

/// Sohbet mesaji domain modeli.
struct ChatMessage: Identifiable, Sendable, Equatable {
    let id: String
    let content: String
    let sender: MessageSender
    let timestamp: Date
    let type: MessageType
    let attachments: [ChatAttachment]
    let isStreaming: Bool

    init(
        id: String = UUID().uuidString,
        content: String,
        sender: MessageSender,
        timestamp: Date = Date(),
        type: MessageType = .text,
        attachments: [ChatAttachment] = [],
        isStreaming: Bool = false
    ) {
        self.id = id
        self.content = content
        self.sender = sender
        self.timestamp = timestamp
        self.type = type
        self.attachments = attachments
        self.isStreaming = isStreaming
    }
}

/// Mesaj gonderici tipi.
enum MessageSender: String, Sendable, Equatable, CaseIterable {
    case user
    case assistant
    case system
}

/// Mesaj icerik tipi.
enum MessageType: String, Sendable, Equatable, CaseIterable {
    case text
    case code
    case image
    case file
    case system
    case codeDiff = "code.diff"
}
