import Foundation

/// Chat mesaji DTO -> Domain donusturucu.
enum ChatMessageMapper {
    /// DTO'yu domain modeline donusturur.
    static func toDomain(_ dto: ChatMessageDTO) -> ChatMessage {
        let dateFormatter = ISO8601DateFormatter()

        return ChatMessage(
            id: dto.id,
            content: dto.content,
            sender: MessageSender(rawValue: dto.sender) ?? .system,
            timestamp: dateFormatter.date(from: dto.timestamp) ?? Date(),
            type: MessageType(rawValue: dto.type) ?? .text
        )
    }

    /// DTO listesini domain modeline donusturur.
    static func toDomain(_ dtos: [ChatMessageDTO]) -> [ChatMessage] {
        dtos.map { toDomain($0) }
    }
}
