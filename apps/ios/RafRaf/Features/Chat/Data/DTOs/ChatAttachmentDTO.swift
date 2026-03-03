import Foundation

/// Chat mesaj eki DTO.
/// `shared/api-contracts/ws/chat-messages.json` ChatAttachment kontratina uygun.
struct ChatAttachmentDTO: Codable, Sendable {
    let id: String
    let type: String
    let url: String
    let mimeType: String
    let sizeBytes: Int
}
