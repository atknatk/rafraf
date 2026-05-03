import Foundation
import Testing
@testable import RafRaf

/// Item 5 — `ChatSessionManager.handleMemoryPressure()` davranis testleri.
///
/// Memory pressure altinda aktif (gorunur) session'in mesajlari korunmali,
/// inactive session'lar `evictOldestMessages` cagirilarak kuculmeli.
@Suite("ChatSessionManager Memory Pressure Tests")
struct ChatSessionManagerMemoryPressureTests {

    // MARK: - Helpers

    @MainActor
    private func makeSUT() -> ChatSessionManager {
        ChatSessionManager(
            sendMessageUseCaseFactory: {
                SendMessageUseCase(repository: MockChatRepository())
            },
            loadHistoryUseCaseFactory: {
                LoadChatHistoryUseCase(repository: MockChatRepository())
            },
            fetchMissedMessagesUseCaseFactory: {
                FetchMissedMessagesUseCase(repository: MockChatRepository())
            }
        )
    }

    @MainActor
    private func seed(_ vm: ChatViewModel, count: Int) {
        for index in 0..<count {
            vm.handleIncomingMessage(ChatMessage(
                id: "\(vm.sessionId)-msg-\(index)",
                content: "msg",
                sender: .assistant,
                timestamp: Date(timeIntervalSince1970: TimeInterval(1_700_000_000 + index))
            ))
        }
    }

    // MARK: - Tests

    @Test("handleMemoryPressure: aktif session korunur, inactive sessionlar evict edilir")
    @MainActor
    func memoryPressure_evictsOnlyInactiveSessions() {
        let manager = makeSUT()

        // 3 farkli session olustur
        let active = manager.viewModel(for: "p-active", agentId: "a1")
        let inactive1 = manager.viewModel(for: "p-inactive-1", agentId: "a2")
        let inactive2 = manager.viewModel(for: "p-inactive-2", agentId: "a3")

        seed(active, count: 250)
        seed(inactive1, count: 250)
        seed(inactive2, count: 250)

        // Active'i secelim
        manager.switchProject(id: "p-active", name: "Active", agentId: "a1")

        manager.handleMemoryPressure()

        // Aktif session korunmali
        #expect(active.messages.count == 250)
        #expect(active.wasEvicted == false)

        // Inactive'ler kuculmeli (250 -> 125 hedef ama min-retain 100)
        #expect(inactive1.messages.count == 125)
        #expect(inactive2.messages.count == 125)
        #expect(inactive1.wasEvicted == true)
        #expect(inactive2.wasEvicted == true)
    }

    @Test("handleMemoryPressure: tek aktif session ise hicbir sey degismez")
    @MainActor
    func memoryPressure_singleActiveSession_noChange() {
        let manager = makeSUT()
        let only = manager.viewModel(for: "p-only", agentId: nil)
        seed(only, count: 250)
        manager.switchProject(id: "p-only", name: "Only", agentId: nil)

        manager.handleMemoryPressure()

        #expect(only.messages.count == 250)
    }

    @Test("resetInactiveSession: inactive session baseline'a doner")
    @MainActor
    func resetInactiveSession_clears() {
        let manager = makeSUT()
        let inactive = manager.viewModel(for: "p-inactive", agentId: "a1")
        seed(inactive, count: 30)

        manager.switchProject(id: "p-other", name: "Other", agentId: "a2")
        manager.resetInactiveSession(agentId: "a1", projectId: "p-inactive")

        #expect(inactive.messages.isEmpty)
    }

    @Test("resetInactiveSession: aktif session SIFIRLANMAZ")
    @MainActor
    func resetInactiveSession_doesNotClearActive() {
        let manager = makeSUT()
        let active = manager.viewModel(for: "p-active", agentId: "a1")
        seed(active, count: 30)
        manager.switchProject(id: "p-active", name: "Active", agentId: "a1")

        manager.resetInactiveSession(agentId: "a1", projectId: "p-active")

        // Korunmali
        #expect(active.messages.count == 30)
    }
}
