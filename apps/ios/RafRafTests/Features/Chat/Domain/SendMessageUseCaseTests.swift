import Foundation
import Testing
@testable import RafRaf

/// SendMessageUseCase testleri.
@Suite("SendMessageUseCase Tests")
struct SendMessageUseCaseTests {

    private func makeSUT(
        repository: MockChatRepository = MockChatRepository()
    ) -> (SendMessageUseCase, MockChatRepository) {
        let useCase = SendMessageUseCase(repository: repository)
        return (useCase, repository)
    }

    @Test("Basarili mesaj gonderme")
    func executeSuccess() async throws {
        let (useCase, repo) = makeSUT()

        let result = try await useCase.execute(text: "Merhaba", sessionId: "session-1")

        #expect(result.sender == .user)
        #expect(repo.sendMessageCallCount == 1)
        #expect(repo.lastSentText == "Merhaba")
        #expect(repo.lastSessionId == "session-1")
    }

    @Test("Bos mesaj gonderme engellenmeli")
    func executeEmptyMessage() async {
        let (useCase, repo) = makeSUT()

        do {
            _ = try await useCase.execute(text: "", sessionId: "session-1")
            Issue.record("Bos mesaj hatasi bekleniyor")
        } catch {
            #expect(error is SendMessageError)
            if let sendError = error as? SendMessageError {
                #expect(sendError == .emptyMessage)
            }
        }

        #expect(repo.sendMessageCallCount == 0)
    }

    @Test("Sadece whitespace iceren mesaj engellenmeli")
    func executeWhitespaceOnly() async {
        let (useCase, repo) = makeSUT()

        do {
            _ = try await useCase.execute(text: "   \n\t  ", sessionId: "session-1")
            Issue.record("Bos mesaj hatasi bekleniyor")
        } catch {
            #expect(error is SendMessageError)
        }

        #expect(repo.sendMessageCallCount == 0)
    }

    @Test("4096 karakterden uzun mesaj engellenmeli")
    func executeTooLongMessage() async {
        let (useCase, repo) = makeSUT()
        let longText = String(repeating: "a", count: 4097)

        do {
            _ = try await useCase.execute(text: longText, sessionId: "session-1")
            Issue.record("Uzun mesaj hatasi bekleniyor")
        } catch {
            #expect(error is SendMessageError)
            if let sendError = error as? SendMessageError {
                #expect(sendError == .messageTooLong(count: 4097, limit: 4096))
            }
        }

        #expect(repo.sendMessageCallCount == 0)
    }

    @Test("4096 karakter sinirinda mesaj kabul edilmeli")
    func executeExactLimitMessage() async throws {
        let (useCase, _) = makeSUT()
        let exactText = String(repeating: "a", count: 4096)

        let result = try await useCase.execute(text: exactText, sessionId: "session-1")
        #expect(result.sender == .user)
    }

    @Test("Mesaj metni trimmed gonderilmeli")
    func executeTrimsWhitespace() async throws {
        let (useCase, repo) = makeSUT()

        _ = try await useCase.execute(text: "  Merhaba  ", sessionId: "session-1")

        #expect(repo.lastSentText == "Merhaba")
    }
}
