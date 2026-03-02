import Foundation

/// Sohbet mesaji domain modeli.
struct ChatMessage: Identifiable, Sendable, Equatable {
    let id: String
    let content: String
    let sender: MessageSender
    let timestamp: Date
    let type: MessageType
}

/// Mesaj gonderici tipi.
enum MessageSender: String, Sendable, Equatable {
    case user
    case assistant
    case system
}

/// Mesaj icerik tipi.
enum MessageType: String, Sendable, Equatable {
    case text
    case voice
    case system
}
