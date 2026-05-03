import Foundation
import Testing
@testable import RafRaf

/// Item 6 — `loadMoreMessages` auto-paginate gating davranis testleri.
///
/// View'in sentinel `.onAppear` tetigi her appear'da fire eder; ViewModel'in
/// `isLoadingMore` flag'i double-fetch'i onlemeli. Mevcut `hasMoreMessages =
/// false` veya `nextCursor == nil` durumlarinda guard zaten erken donmeli.
@Suite("ChatViewModel Auto Paginate Tests")
struct ChatViewModelAutoPaginateTests {

    // MARK: - Helpers

    @MainActor
    private func makeSUT(
        repository: MockChatRepository = MockChatRepository()
    ) -> (ChatViewModel, MockChatRepository) {
        let vm = ChatViewModel(
            sendMessageUseCase: SendMessageUseCase(repository: repository),
            loadHistoryUseCase: LoadChatHistoryUseCase(repository: repository),
            sessionId: "auto-paginate-test"
        )
        return (vm, repository)
    }

    // MARK: - Guard: hasMoreMessages == false

    @Test("loadMoreMessages: hasMoreMessages false ise repo cagrilmaz")
    @MainActor
    func loadMore_hasMoreFalse_skipsRepo() async {
        let (vm, repo) = makeSUT()
        vm.hasMoreMessages = false

        await vm.loadMoreMessages()

        #expect(repo.loadHistoryCallCount == 0)
        #expect(vm.isLoadingMore == false)
    }

    // MARK: - Guard: missing cursor

    @Test("loadMoreMessages: nextCursor nil ise repo cagrilmaz")
    @MainActor
    func loadMore_noCursor_skipsRepo() async {
        let repo = MockChatRepository()
        // Initial loadHistory ile hasMoreMessages = true ama nextCursor = nil
        repo.loadHistoryResult = .success(
            ChatHistoryResult(messages: [], hasMore: true, nextCursor: nil)
        )
        let (vm, _) = makeSUT(repository: repo)
        await vm.loadHistory()
        #expect(vm.hasMoreMessages == true)

        let beforeCount = repo.loadHistoryCallCount
        await vm.loadMoreMessages()

        // loadMoreMessages icindeki cagri yapilmamali (cursor yoktu)
        #expect(repo.loadHistoryCallCount == beforeCount)
    }

    // MARK: - Auto-paginate: success path

    @Test("loadMoreMessages: ilk cagri eski mesajlari basa eklemeli")
    @MainActor
    func loadMore_success_prependsMessages() async {
        let repo = MockChatRepository()
        let recent = [
            ChatMessage(id: "m2", content: "recent", sender: .user, timestamp: Date(timeIntervalSince1970: 200))
        ]
        repo.loadHistoryResult = .success(
            ChatHistoryResult(messages: recent, hasMore: true, nextCursor: "cursor-1")
        )
        let (vm, _) = makeSUT(repository: repo)
        await vm.loadHistory()
        #expect(vm.messages.count == 1)
        #expect(vm.hasMoreMessages == true)

        let older = [
            ChatMessage(id: "m1", content: "older", sender: .assistant, timestamp: Date(timeIntervalSince1970: 100))
        ]
        repo.loadHistoryResult = .success(
            ChatHistoryResult(messages: older, hasMore: false, nextCursor: nil)
        )

        await vm.loadMoreMessages()

        #expect(vm.messages.count == 2)
        #expect(vm.messages.first?.id == "m1")
        #expect(vm.hasMoreMessages == false)
        #expect(vm.isLoadingMore == false)
    }

    // MARK: - Reset: isLoadingMore exposed flag stays observable

    @Test("loadMoreMessages: tamamlandiktan sonra isLoadingMore false olmali")
    @MainActor
    func loadMore_finishesWithFalseFlag() async {
        let repo = MockChatRepository()
        repo.loadHistoryResult = .success(
            ChatHistoryResult(messages: [], hasMore: true, nextCursor: "x")
        )
        let (vm, _) = makeSUT(repository: repo)
        await vm.loadHistory()

        repo.loadHistoryResult = .success(
            ChatHistoryResult(messages: [], hasMore: false, nextCursor: nil)
        )
        await vm.loadMoreMessages()

        #expect(vm.isLoadingMore == false)
    }
}
