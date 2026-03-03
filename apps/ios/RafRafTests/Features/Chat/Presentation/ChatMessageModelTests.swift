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
    }

    @Test("MessageSender tum varyantlari mevcut olmali")
    func messageSenderVariants() {
        let senders: [MessageSender] = [.user, .assistant, .system]
        #expect(senders.count == 3)
    }

    @Test("MessageType tum varyantlari mevcut olmali")
    func messageTypeVariants() {
        let types: [MessageType] = [.text, .voice, .system]
        #expect(types.count == 3)
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
}
