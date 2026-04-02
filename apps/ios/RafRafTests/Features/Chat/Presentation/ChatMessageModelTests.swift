import Foundation
import Testing
@testable import RafRaf

/// ChatMessage domain model testleri.
@Suite("ChatMessage Model Tests")
struct ChatMessageModelTests {

    @Test("ChatMessage olusturulabilmeli")
    func chatMessageCreation() {
        let message = ChatMessage(
            id: "msg-1",
            content: "Merhaba",
            sender: .user,
            timestamp: Date(),
            type: .text
        )

        #expect(message.id == "msg-1")
        #expect(message.content == "Merhaba")
        #expect(message.sender == .user)
        #expect(message.type == .text)
        #expect(message.attachments.isEmpty)
        #expect(message.isStreaming == false)
    }

    @Test("ChatMessage varsayilan degerlerle olusturulabilmeli")
    func chatMessageDefaultValues() {
        let message = ChatMessage(content: "Test", sender: .assistant)

        #expect(!message.id.isEmpty)
        #expect(message.content == "Test")
        #expect(message.sender == .assistant)
        #expect(message.type == .text)
        #expect(message.attachments.isEmpty)
        #expect(message.isStreaming == false)
    }

    @Test("ChatMessage streaming durumu ayarlanabilmeli")
    func chatMessageStreaming() {
        let message = ChatMessage(
            content: "Streaming...",
            sender: .assistant,
            isStreaming: true
        )

        #expect(message.isStreaming == true)
    }

    @Test("ChatMessage attachment'li olusturulabilmeli")
    func chatMessageWithAttachments() {
        let attachment = ChatAttachment(
            type: .image,
            url: "https://example.com/image.png",
            mimeType: "image/png",
            sizeBytes: 1024
        )

        let message = ChatMessage(
            content: "Gorsel",
            sender: .assistant,
            type: .image,
            attachments: [attachment]
        )

        #expect(message.attachments.count == 1)
        #expect(message.attachments.first?.type == .image)
    }

    @Test("MessageSender tum varyantlari mevcut olmali")
    func messageSenderVariants() {
        let senders = MessageSender.allCases
        #expect(senders.count == 3)
        #expect(senders.contains(.user))
        #expect(senders.contains(.assistant))
        #expect(senders.contains(.system))
    }

    @Test("MessageType tum varyantlari mevcut olmali")
    func messageTypeVariants() {
        let types = MessageType.allCases
        #expect(types.count == 6)
        #expect(types.contains(.text))
        #expect(types.contains(.code))
        #expect(types.contains(.image))
        #expect(types.contains(.file))
        #expect(types.contains(.system))
        #expect(types.contains(.codeDiff))
    }

    @Test("ChatMessage Equatable uyumlu olmali")
    func chatMessageEquatable() {
        let date = Date()
        let msg1 = ChatMessage(id: "1", content: "test", sender: .user, timestamp: date, type: .text)
        let msg2 = ChatMessage(id: "1", content: "test", sender: .user, timestamp: date, type: .text)

        #expect(msg1 == msg2)
    }

    @Test("ChatMessage farkli id'ler esit olmamali")
    func chatMessageNotEqual() {
        let date = Date()
        let msg1 = ChatMessage(id: "1", content: "test", sender: .user, timestamp: date, type: .text)
        let msg2 = ChatMessage(id: "2", content: "test", sender: .user, timestamp: date, type: .text)

        #expect(msg1 != msg2)
    }

    @Test("MessageSender rawValue dogru olmali")
    func messageSenderRawValues() {
        #expect(MessageSender.user.rawValue == "user")
        #expect(MessageSender.assistant.rawValue == "assistant")
        #expect(MessageSender.system.rawValue == "system")
    }

    @Test("MessageType rawValue dogru olmali")
    func messageTypeRawValues() {
        #expect(MessageType.text.rawValue == "text")
        #expect(MessageType.code.rawValue == "code")
        #expect(MessageType.image.rawValue == "image")
        #expect(MessageType.file.rawValue == "file")
        #expect(MessageType.system.rawValue == "system")
    }
}

/// ChatAttachment domain model testleri.
@Suite("ChatAttachment Model Tests")
struct ChatAttachmentModelTests {

    @Test("ChatAttachment olusturulabilmeli")
    func chatAttachmentCreation() {
        let attachment = ChatAttachment(
            id: "att-1",
            type: .image,
            url: "https://example.com/image.png",
            mimeType: "image/png",
            sizeBytes: 2048
        )

        #expect(attachment.id == "att-1")
        #expect(attachment.type == .image)
        #expect(attachment.url == "https://example.com/image.png")
        #expect(attachment.mimeType == "image/png")
        #expect(attachment.sizeBytes == 2048)
    }

    @Test("ChatAttachment varsayilan id ile olusturulabilmeli")
    func chatAttachmentDefaultId() {
        let attachment = ChatAttachment(
            type: .file,
            url: "https://example.com/doc.pdf",
            mimeType: "application/pdf",
            sizeBytes: 4096
        )

        #expect(!attachment.id.isEmpty)
    }

    @Test("AttachmentType tum varyantlari mevcut olmali")
    func attachmentTypeVariants() {
        let types = AttachmentType.allCases
        #expect(types.count == 3)
        #expect(types.contains(.image))
        #expect(types.contains(.file))
        #expect(types.contains(.audio))
    }

    @Test("ChatAttachment Equatable uyumlu olmali")
    func chatAttachmentEquatable() {
        let att1 = ChatAttachment(id: "1", type: .image, url: "url", mimeType: "image/png", sizeBytes: 100)
        let att2 = ChatAttachment(id: "1", type: .image, url: "url", mimeType: "image/png", sizeBytes: 100)

        #expect(att1 == att2)
    }
}

/// ChatHistoryResult model testleri.
@Suite("ChatHistoryResult Model Tests")
struct ChatHistoryResultModelTests {

    @Test("ChatHistoryResult bos sonuc olusturulabilmeli")
    func emptyResult() {
        let result = ChatHistoryResult(messages: [], hasMore: false, nextCursor: nil)

        #expect(result.messages.isEmpty)
        #expect(result.hasMore == false)
        #expect(result.nextCursor == nil)
    }

    @Test("ChatHistoryResult mesajli sonuc olusturulabilmeli")
    func resultWithMessages() {
        let messages = [
            ChatMessage(content: "Msg1", sender: .user),
            ChatMessage(content: "Msg2", sender: .assistant)
        ]

        let result = ChatHistoryResult(
            messages: messages,
            hasMore: true,
            nextCursor: "cursor-123"
        )

        #expect(result.messages.count == 2)
        #expect(result.hasMore == true)
        #expect(result.nextCursor == "cursor-123")
    }
}
