import Foundation
import Testing
@testable import RafRaf

/// Item 5 — ChatViewModel LRU eviction & inactive-session reset davranis testleri.
///
/// `evictOldestMessages()` icin minimum threshold, oldest-half kuralı ve
/// sentinel min-retention (`lruMinimumRetainedMessages`) garantilerini
/// dogrular. Ayrica `resetForInactiveSession()` baseline'a doner.
@Suite("ChatViewModel Memory Pressure Tests")
struct ChatViewModelMemoryPressureTests {

    // MARK: - Helpers

    @MainActor
    private func makeSUT() -> ChatViewModel {
        let repo = MockChatRepository()
        return ChatViewModel(
            sendMessageUseCase: SendMessageUseCase(repository: repo),
            loadHistoryUseCase: LoadChatHistoryUseCase(repository: repo),
            sessionId: "lru-test"
        )
    }

    @MainActor
    private func seedMessages(_ vm: ChatViewModel, count: Int) {
        for index in 0..<count {
            vm.handleIncomingMessage(ChatMessage(
                id: "msg-\(index)",
                content: "msg \(index)",
                sender: .assistant,
                timestamp: Date(timeIntervalSince1970: TimeInterval(1_700_000_000 + index))
            ))
        }
    }

    // MARK: - Threshold

    @Test("evictOldestMessages: minimum esik altinda no-op olmali")
    @MainActor
    func eviction_belowThreshold_isNoop() {
        let vm = makeSUT()
        seedMessages(vm, count: 50) // < lruMinimumRetainedMessages (100)

        let evicted = vm.evictOldestMessages()

        #expect(evicted == 0)
        #expect(vm.messages.count == 50)
        #expect(vm.wasEvicted == false)
    }

    @Test("evictOldestMessages: tam esik degerinde de no-op")
    @MainActor
    func eviction_atThreshold_isNoop() {
        let vm = makeSUT()
        seedMessages(vm, count: 100)

        let evicted = vm.evictOldestMessages()

        #expect(evicted == 0)
        #expect(vm.messages.count == 100)
    }

    // MARK: - Half-cut

    @Test("evictOldestMessages: 200 mesajdan 100 atilmali (oldest half)")
    @MainActor
    func eviction_doubleThreshold_dropsOldestHalf() {
        let vm = makeSUT()
        seedMessages(vm, count: 200)

        let evicted = vm.evictOldestMessages()

        #expect(evicted == 100)
        #expect(vm.messages.count == 100)
        // En yeni mesajlar korunmali
        #expect(vm.messages.first?.id == "msg-100")
        #expect(vm.messages.last?.id == "msg-199")
        #expect(vm.wasEvicted == true)
        #expect(vm.hasMoreMessages == true)
    }

    @Test("evictOldestMessages: minimum-retain garantisi (150 -> 100 kalir)")
    @MainActor
    func eviction_respectsMinimumRetention() {
        let vm = makeSUT()
        seedMessages(vm, count: 150)

        let evicted = vm.evictOldestMessages()

        // half = 75 ama min-retain = 100, dolayisiyla en fazla 50 atilabilir.
        #expect(evicted == 50)
        #expect(vm.messages.count == 100)
        #expect(vm.messages.first?.id == "msg-50")
        #expect(vm.messages.last?.id == "msg-149")
    }

    // MARK: - Reset

    @Test("resetForInactiveSession: tum mesajlar ve volatile state sifirlanmali")
    @MainActor
    func resetForInactive_clearsState() {
        let vm = makeSUT()
        seedMessages(vm, count: 30)
        vm.pendingSuggestions = ["a", "b"]
        vm.suggestionMessageId = "s1"
        vm.handleProgress(ProgressMessageContent(
            task: "task",
            step: 1,
            totalSteps: 3,
            percentage: 33,
            details: nil,
            phase: "running",
            stepsDetail: nil
        ))

        vm.resetForInactiveSession()

        #expect(vm.messages.isEmpty)
        #expect(vm.pendingSuggestions.isEmpty)
        #expect(vm.suggestionMessageId == nil)
        #expect(vm.currentActivity == nil)
        #expect(vm.hasMoreMessages == false)
    }

    // MARK: - hasMoreMessages flip

    @Test("evictOldestMessages: hasMoreMessages true olur ki kullanici geri yukleyebilsin")
    @MainActor
    func eviction_setsHasMoreMessagesTrue() {
        let vm = makeSUT()
        seedMessages(vm, count: 250)
        // Once false ki sahnenin baslangici net olsun
        vm.hasMoreMessages = false

        _ = vm.evictOldestMessages()

        #expect(vm.hasMoreMessages == true)
    }
}
