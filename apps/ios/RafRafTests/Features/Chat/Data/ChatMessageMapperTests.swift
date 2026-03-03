import Foundation
import Testing
@testable import RafRaf

/// ChatMessageMapper testleri.
@Suite("ChatMessageMapper Tests")
struct ChatMessageMapperTests {

    @Test("DTO'dan domain modeline donusum")
    func toDomainSingleMessage() {
        let dto = ChatMessageDTO(
            messageId: "msg-123",
            text: "Merhaba",
            sender: "user",
            type: "text",
            timestamp: "2026-03-03T12:00:00Z",
            attachments: nil
        )

        let message = ChatMessageMapper.toDomain(dto)

        #expect(message.id == "msg-123")
        #expect(message.content == "Merhaba")
        #expect(message.sender == .user)
        #expect(message.type == .text)
        #expect(message.attachments.isEmpty)
    }

    @Test("DTO listesinden domain model listesine donusum")
    func toDomainList() {
        let dtos = [
            ChatMessageDTO(
                messageId: "1", text: "Msg1", sender: "user",
                type: "text", timestamp: "2026-03-03T12:00:00Z", attachments: nil
            ),
            ChatMessageDTO(
                messageId: "2", text: "Msg2", sender: "assistant",
                type: "code", timestamp: "2026-03-03T12:01:00Z", attachments: nil
            )
        ]

        let messages = ChatMessageMapper.toDomain(dtos)

        #expect(messages.count == 2)
        #expect(messages[0].sender == .user)
        #expect(messages[1].sender == .assistant)
        #expect(messages[1].type == .code)
    }

    @Test("Bilinmeyen sender system olarak eslenmeili")
    func toDomainUnknownSender() {
        let dto = ChatMessageDTO(
            messageId: "1", text: "Test", sender: "unknown_sender",
            type: "text", timestamp: "2026-03-03T12:00:00Z", attachments: nil
        )

        let message = ChatMessageMapper.toDomain(dto)

        #expect(message.sender == .system)
    }

    @Test("Bilinmeyen type text olarak eslenmeli")
    func toDomainUnknownType() {
        let dto = ChatMessageDTO(
            messageId: "1", text: "Test", sender: "user",
            type: "unknown_type", timestamp: "2026-03-03T12:00:00Z", attachments: nil
        )

        let message = ChatMessageMapper.toDomain(dto)

        #expect(message.type == .text)
    }

    @Test("Gecersiz timestamp simdi olarak eslenmeli")
    func toDomainInvalidTimestamp() {
        let dto = ChatMessageDTO(
            messageId: "1", text: "Test", sender: "user",
            type: "text", timestamp: "gecersiz-tarih", attachments: nil
        )

        let message = ChatMessageMapper.toDomain(dto)

        // Gecersiz tarih Date() olarak eslenmeli (yaklasik olarak su an)
        let now = Date()
        let difference = abs(message.timestamp.timeIntervalSince(now))
        #expect(difference < 5.0) // 5 saniye tolerans
    }

    @Test("Attachment DTO'dan domain modeline donusum")
    func toDomainAttachment() {
        let attachmentDTO = ChatAttachmentDTO(
            id: "att-1",
            type: "image",
            url: "https://example.com/img.png",
            mimeType: "image/png",
            sizeBytes: 2048
        )

        let attachment = ChatMessageMapper.toDomain(attachmentDTO)

        #expect(attachment.id == "att-1")
        #expect(attachment.type == .image)
        #expect(attachment.url == "https://example.com/img.png")
        #expect(attachment.mimeType == "image/png")
        #expect(attachment.sizeBytes == 2048)
    }

    @Test("Bilinmeyen attachment type file olarak eslenmeli")
    func toDomainUnknownAttachmentType() {
        let attachmentDTO = ChatAttachmentDTO(
            id: "att-1",
            type: "unknown",
            url: "https://example.com/file",
            mimeType: "application/octet-stream",
            sizeBytes: 100
        )

        let attachment = ChatMessageMapper.toDomain(attachmentDTO)

        #expect(attachment.type == .file)
    }

    @Test("Mesaj attachment'lar ile donusum")
    func toDomainWithAttachments() {
        let dto = ChatMessageDTO(
            messageId: "1",
            text: "Gorsel",
            sender: "assistant",
            type: "image",
            timestamp: "2026-03-03T12:00:00Z",
            attachments: [
                ChatAttachmentDTO(
                    id: "att-1",
                    type: "image",
                    url: "https://example.com/img.png",
                    mimeType: "image/png",
                    sizeBytes: 1024
                )
            ]
        )

        let message = ChatMessageMapper.toDomain(dto)

        #expect(message.attachments.count == 1)
        #expect(message.attachments.first?.type == .image)
    }

    @Test("ChatHistoryResponse donusum")
    func toDomainHistoryResponse() {
        let historyDTO = ChatHistoryResponseDTO(
            messages: [
                ChatMessageDTO(
                    messageId: "1", text: "Msg1", sender: "user",
                    type: "text", timestamp: "2026-03-03T12:00:00Z", attachments: nil
                )
            ],
            hasMore: true,
            nextCursor: "cursor-abc"
        )

        let result = ChatMessageMapper.toDomain(historyDTO)

        #expect(result.messages.count == 1)
        #expect(result.hasMore == true)
        #expect(result.nextCursor == "cursor-abc")
    }

    @Test("Bos history response donusum")
    func toDomainEmptyHistoryResponse() {
        let historyDTO = ChatHistoryResponseDTO(
            messages: [],
            hasMore: false,
            nextCursor: nil
        )

        let result = ChatMessageMapper.toDomain(historyDTO)

        #expect(result.messages.isEmpty)
        #expect(result.hasMore == false)
        #expect(result.nextCursor == nil)
    }

    @Test("Fractional seconds timestamp desteklenmeli")
    func toDomainFractionalSecondsTimestamp() {
        let dto = ChatMessageDTO(
            messageId: "1", text: "Test", sender: "user",
            type: "text", timestamp: "2026-03-03T12:00:00.123Z", attachments: nil
        )

        let message = ChatMessageMapper.toDomain(dto)

        // Fractional seconds ile tarih dogru parse edilmeli
        let calendar = Calendar.current
        let components = calendar.dateComponents(in: TimeZone(abbreviation: "UTC")!, from: message.timestamp)
        #expect(components.year == 2026)
        #expect(components.month == 3)
        #expect(components.day == 3)
    }
}
