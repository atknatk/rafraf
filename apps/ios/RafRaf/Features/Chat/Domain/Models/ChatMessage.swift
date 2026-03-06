import Foundation

/// Kullanicinin AI yanitina verdigi degerlendirme.
enum MessageRating: String, Sendable, Codable, Equatable {
    case up
    case down
}

/// Sohbet mesaji domain modeli.
struct ChatMessage: Identifiable, Sendable, Equatable {
    let id: String
    let content: String
    let sender: MessageSender
    let timestamp: Date
    let type: MessageType
    let attachments: [ChatAttachment]
    let isStreaming: Bool
    /// Toplam token sayisi (input + output). Sadece assistant mesajlarinda dolu olur.
    let tokensUsed: Int?
    /// Kullanilan model adi. Sadece assistant mesajlarinda dolu olur.
    let modelUsed: String?
    /// Kullanicinin verdigi degerlendirme (thumbs up/down).
    let rating: MessageRating?

    init(
        id: String = UUID().uuidString,
        content: String,
        sender: MessageSender,
        timestamp: Date = Date(),
        type: MessageType = .text,
        attachments: [ChatAttachment] = [],
        isStreaming: Bool = false,
        tokensUsed: Int? = nil,
        modelUsed: String? = nil,
        rating: MessageRating? = nil
    ) {
        self.id = id
        self.content = content
        self.sender = sender
        self.timestamp = timestamp
        self.type = type
        self.attachments = attachments
        self.isStreaming = isStreaming
        self.tokensUsed = tokensUsed
        self.modelUsed = modelUsed
        self.rating = rating
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
