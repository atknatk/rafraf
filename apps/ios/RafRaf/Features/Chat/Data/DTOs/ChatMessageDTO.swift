import Foundation

/// Chat mesaji API response DTO.
struct ChatMessageDTO: Codable, Sendable {
    let id: String
    let content: String
    let sender: String
    let timestamp: String
    let type: String
}
