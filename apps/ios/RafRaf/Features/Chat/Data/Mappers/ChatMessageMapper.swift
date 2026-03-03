import Foundation

/// Chat mesaji DTO -> Domain donusturucu.
enum ChatMessageMapper {
    private static let dateFormatter: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter
    }()

    private static let fallbackDateFormatter: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        return formatter
    }()

    /// DTO'yu domain modeline donusturur.
    static func toDomain(_ dto: ChatMessageDTO) -> ChatMessage {
        let date = dateFormatter.date(from: dto.timestamp)
            ?? fallbackDateFormatter.date(from: dto.timestamp)
            ?? Date()

        let attachments = dto.attachments?.map { toDomain($0) } ?? []

        return ChatMessage(
            id: dto.messageId,
            content: dto.text,
            sender: MessageSender(rawValue: dto.sender) ?? .system,
            timestamp: date,
            type: MessageType(rawValue: dto.type) ?? .text,
            attachments: attachments
        )
    }

    /// DTO listesini domain modeline donusturur.
    static func toDomain(_ dtos: [ChatMessageDTO]) -> [ChatMessage] {
        dtos.map { toDomain($0) }
    }

    /// Attachment DTO'yu domain modeline donusturur.
    static func toDomain(_ dto: ChatAttachmentDTO) -> ChatAttachment {
        ChatAttachment(
            id: dto.id,
            type: AttachmentType(rawValue: dto.type) ?? .file,
            url: dto.url,
            mimeType: dto.mimeType,
            sizeBytes: dto.sizeBytes
        )
    }

    /// Chat gecmis response'u domain modeline donusturur.
    static func toDomain(_ dto: ChatHistoryResponseDTO) -> ChatHistoryResult {
        ChatHistoryResult(
            messages: toDomain(dto.messages),
            hasMore: dto.hasMore,
            nextCursor: dto.nextCursor
        )
    }
}
