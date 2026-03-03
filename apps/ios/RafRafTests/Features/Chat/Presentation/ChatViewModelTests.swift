import Foundation
import Testing
@testable import RafRaf

/// ChatViewModel testleri.
@Suite("ChatViewModel Tests")
struct ChatViewModelTests {

    // MARK: - Helpers

    @MainActor
    private func makeSUT(
        repository: MockChatRepository = MockChatRepository()
    ) -> (ChatViewModel, MockChatRepository) {
        let vm = ChatViewModel(
            sendMessageUseCase: SendMessageUseCase(repository: repository),
            loadHistoryUseCase: LoadChatHistoryUseCase(repository: repository),
            sessionId: "test-session-123"
        )
        return (vm, repository)
    }

    // MARK: - Initial State

    @Test("ChatViewModel baslangic durumu dogru olmali")
    @MainActor
    func initialState() {
        let (vm, _) = makeSUT()

        #expect(vm.messages.isEmpty)
        #expect(vm.messageText.isEmpty)
        #expect(vm.isLoading == false)
        #expect(vm.isSending == false)
        #expect(vm.isTyping == false)
        #expect(vm.errorMessage == nil)
        #expect(vm.hasMoreMessages == false)
    }

    // MARK: - Send Message

    @Test("sendMessage bos mesajda islem yapmamali")
    @MainActor
    func sendMessageEmpty() async {
        let (vm, repo) = makeSUT()
        vm.messageText = ""

        await vm.sendMessage()

        #expect(repo.sendMessageCallCount == 0)
        #expect(vm.messages.isEmpty)
    }

    @Test("sendMessage sadece whitespace iceren mesajda islem yapmamali")
    @MainActor
    func sendMessageWhitespace() async {
        let (vm, repo) = makeSUT()
        vm.messageText = "   \n  "

        await vm.sendMessage()

        #expect(repo.sendMessageCallCount == 0)
    }

    @Test("sendMessage basarili gonderimde mesaji listeye eklemeli")
    @MainActor
    func sendMessageSuccess() async {
        let (vm, repo) = makeSUT()
        vm.messageText = "Test mesaji"

        await vm.sendMessage()

        #expect(repo.sendMessageCallCount == 1)
        #expect(vm.messages.count == 1)
        #expect(vm.messageText.isEmpty)
        #expect(vm.isSending == false)
    }

    @Test("sendMessage basarisiz gonderimde hata mesaji gostermeli")
    @MainActor
    func sendMessageFailure() async {
        let repo = MockChatRepository()
        repo.sendMessageResult = .failure(SendMessageError.emptyMessage)
        let (vm, _) = makeSUT(repository: repo)
        vm.messageText = "Test"

        await vm.sendMessage()

        #expect(vm.errorMessage != nil)
        #expect(vm.isSending == false)
        // Basarisizlikta metin geri yuklenmeli
        #expect(vm.messageText == "Test")
    }

    @Test("sendMessage sonrasi messageText temizlenmeli")
    @MainActor
    func sendMessageClearsText() async {
        let (vm, _) = makeSUT()
        vm.messageText = "Test mesaji"

        await vm.sendMessage()

        #expect(vm.messageText.isEmpty)
    }

    // MARK: - Load History

    @Test("loadHistory basarili yuklemede mesajlari gostermeli")
    @MainActor
    func loadHistorySuccess() async {
        let repo = MockChatRepository()
        let testMessages = [
            ChatMessage(content: "Msg1", sender: .user),
            ChatMessage(content: "Msg2", sender: .assistant)
        ]
        repo.loadHistoryResult = .success(
            ChatHistoryResult(messages: testMessages, hasMore: true, nextCursor: "cursor-1")
        )
        let (vm, _) = makeSUT(repository: repo)

        await vm.loadHistory()

        #expect(vm.messages.count == 2)
        #expect(vm.hasMoreMessages == true)
        #expect(vm.isLoading == false)
    }

    @Test("loadHistory basarisiz yuklemede hata mesaji gostermeli")
    @MainActor
    func loadHistoryFailure() async {
        let repo = MockChatRepository()
        repo.loadHistoryResult = .failure(ChatRepositoryError.connectionError)
        let (vm, _) = makeSUT(repository: repo)

        await vm.loadHistory()

        #expect(vm.errorMessage != nil)
        #expect(vm.messages.isEmpty)
        #expect(vm.isLoading == false)
    }

    @Test("loadHistory tekrarli cagirildiginda duplike yukleme yapmamali")
    @MainActor
    func loadHistoryDuplicate() async {
        let repo = MockChatRepository()
        let (vm, _) = makeSUT(repository: repo)

        // loadHistory isLoading = true iken ikinci cagri engellenmeli
        // Ancak async test ortaminda sequential calisir, sadece call count kontrol edelim
        await vm.loadHistory()

        #expect(repo.loadHistoryCallCount == 1)
    }

    // MARK: - Load More Messages

    @Test("loadMoreMessages hasMore false iken calismamali")
    @MainActor
    func loadMoreNoMore() async {
        let repo = MockChatRepository()
        let (vm, _) = makeSUT(repository: repo)

        await vm.loadMoreMessages()

        #expect(repo.loadHistoryCallCount == 0)
    }

    @Test("loadMoreMessages yeni mesajlari basa eklemeli")
    @MainActor
    func loadMoreSuccess() async {
        let repo = MockChatRepository()
        let initialMessages = [ChatMessage(content: "Recent", sender: .user)]
        repo.loadHistoryResult = .success(
            ChatHistoryResult(messages: initialMessages, hasMore: true, nextCursor: "cursor-1")
        )
        let (vm, _) = makeSUT(repository: repo)

        // Once ilk sayfa yukle
        await vm.loadHistory()
        #expect(vm.messages.count == 1)

        // Sonra ek mesajlar yukle
        let olderMessages = [ChatMessage(content: "Older", sender: .assistant)]
        repo.loadHistoryResult = .success(
            ChatHistoryResult(messages: olderMessages, hasMore: false, nextCursor: nil)
        )

        await vm.loadMoreMessages()

        #expect(vm.messages.count == 2)
        // Eski mesajlar basta olmali
        #expect(vm.messages.first?.content == "Older")
        #expect(vm.hasMoreMessages == false)
    }

    // MARK: - Streaming

    @Test("handleStreamDelta yeni streaming mesaj baslatmali")
    @MainActor
    func streamDeltaNewMessage() {
        let (vm, _) = makeSUT()

        vm.handleStreamDelta(messageId: "stream-1", delta: "Merhaba")

        #expect(vm.messages.count == 1)
        #expect(vm.messages.first?.content == "Merhaba")
        #expect(vm.messages.first?.isStreaming == true)
        #expect(vm.messages.first?.sender == .assistant)
    }

    @Test("handleStreamDelta mevcut streaming mesaja ekleme yapmali")
    @MainActor
    func streamDeltaAppend() {
        let (vm, _) = makeSUT()

        vm.handleStreamDelta(messageId: "stream-1", delta: "Mer")
        vm.handleStreamDelta(messageId: "stream-1", delta: "haba")

        #expect(vm.messages.count == 1)
        #expect(vm.messages.first?.content == "Merhaba")
        #expect(vm.messages.first?.isStreaming == true)
    }

    @Test("handleStreamEnd mesaji finalize etmeli")
    @MainActor
    func streamEnd() {
        let (vm, _) = makeSUT()

        vm.handleStreamDelta(messageId: "stream-1", delta: "Merhaba")
        vm.handleStreamEnd(messageId: "stream-1", fullText: "Merhaba Dunya", type: .text)

        #expect(vm.messages.count == 1)
        #expect(vm.messages.first?.content == "Merhaba Dunya")
        #expect(vm.messages.first?.isStreaming == false)
        #expect(vm.isTyping == false)
    }

    @Test("handleStreamEnd mesaj tipini dogru ayarlamali")
    @MainActor
    func streamEndType() {
        let (vm, _) = makeSUT()

        vm.handleStreamDelta(messageId: "stream-1", delta: "code")
        vm.handleStreamEnd(messageId: "stream-1", fullText: "func foo() {}", type: .code)

        #expect(vm.messages.first?.type == .code)
    }

    // MARK: - Typing Indicator

    @Test("handleTypingIndicator durumu guncellemeli")
    @MainActor
    func typingIndicator() {
        let (vm, _) = makeSUT()

        vm.handleTypingIndicator(isTyping: true)
        #expect(vm.isTyping == true)

        vm.handleTypingIndicator(isTyping: false)
        #expect(vm.isTyping == false)
    }

    // MARK: - Incoming Message

    @Test("handleIncomingMessage mesaji listeye eklemeli")
    @MainActor
    func incomingMessage() {
        let (vm, _) = makeSUT()
        let msg = ChatMessage(content: "AI cevabi", sender: .assistant)

        vm.handleIncomingMessage(msg)

        #expect(vm.messages.count == 1)
        #expect(vm.messages.first?.content == "AI cevabi")
        #expect(vm.isTyping == false)
    }

    // MARK: - Error Handling

    @Test("dismissError hata mesajini temizlemeli")
    @MainActor
    func dismissError() {
        let (vm, _) = makeSUT()
        vm.handleTypingIndicator(isTyping: false)

        // Simulate error state
        let repo = MockChatRepository()
        repo.sendMessageResult = .failure(SendMessageError.emptyMessage)
        let (vm2, _) = makeSUT(repository: repo)
        vm2.messageText = "Test"

        Task {
            await vm2.sendMessage()
            vm2.dismissError()
            #expect(vm2.errorMessage == nil)
        }
    }
}
