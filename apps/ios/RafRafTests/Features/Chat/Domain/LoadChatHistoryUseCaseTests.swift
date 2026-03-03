import Foundation
import Testing
@testable import RafRaf

/// LoadChatHistoryUseCase testleri.
@Suite("LoadChatHistoryUseCase Tests")
struct LoadChatHistoryUseCaseTests {

    private func makeSUT(
        repository: MockChatRepository = MockChatRepository()
    ) -> (LoadChatHistoryUseCase, MockChatRepository) {
        let useCase = LoadChatHistoryUseCase(repository: repository)
        return (useCase, repository)
    }

    @Test("Basarili gecmis yukleme")
    func executeSuccess() async throws {
        let repo = MockChatRepository()
        let testMessages = [
            ChatMessage(content: "Msg1", sender: .user),
            ChatMessage(content: "Msg2", sender: .assistant)
        ]
        repo.loadHistoryResult = .success(
            ChatHistoryResult(messages: testMessages, hasMore: true, nextCursor: "next")
        )
        let (useCase, _) = makeSUT(repository: repo)

        let result = try await useCase.execute(sessionId: "session-1")

        #expect(result.messages.count == 2)
        #expect(result.hasMore == true)
        #expect(result.nextCursor == "next")
        #expect(repo.loadHistoryCallCount == 1)
        #expect(repo.lastSessionId == "session-1")
    }

    @Test("Cursor ile gecmis yukleme")
    func executeWithCursor() async throws {
        let (useCase, repo) = makeSUT()

        _ = try await useCase.execute(sessionId: "session-1", cursor: "cursor-abc")

        #expect(repo.lastCursor == "cursor-abc")
    }

    @Test("Cursor olmadan ilk sayfa yukleme")
    func executeWithoutCursor() async throws {
        let (useCase, repo) = makeSUT()

        _ = try await useCase.execute(sessionId: "session-1")

        #expect(repo.lastCursor == nil)
    }

    @Test("Limit varsayilan 20 olmali")
    func executeDefaultLimit() async throws {
        let (useCase, repo) = makeSUT()

        _ = try await useCase.execute(sessionId: "session-1")

        #expect(repo.lastLimit == 20)
    }

    @Test("Limit 50'den buyuk deger 50'ye clamp edilmeli")
    func executeLimitClampMax() async throws {
        let (useCase, repo) = makeSUT()

        _ = try await useCase.execute(sessionId: "session-1", limit: 100)

        #expect(repo.lastLimit == 50)
    }

    @Test("Limit 0 veya negatif deger 1'e clamp edilmeli")
    func executeLimitClampMin() async throws {
        let (useCase, repo) = makeSUT()

        _ = try await useCase.execute(sessionId: "session-1", limit: 0)

        #expect(repo.lastLimit == 1)
    }

    @Test("Basarisiz gecmis yukleme hata firlatmali")
    func executeFailure() async {
        let repo = MockChatRepository()
        repo.loadHistoryResult = .failure(ChatRepositoryError.connectionError)
        let (useCase, _) = makeSUT(repository: repo)

        do {
            _ = try await useCase.execute(sessionId: "session-1")
            Issue.record("Hata bekleniyor")
        } catch {
            #expect(error is ChatRepositoryError)
        }
    }
}
