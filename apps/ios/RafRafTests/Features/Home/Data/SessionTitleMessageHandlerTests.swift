import Foundation
import Testing
@testable import RafRaf

/// `SessionTitleMessageHandler` testleri.
@Suite("SessionTitleMessageHandler Tests")
struct SessionTitleMessageHandlerTests {

    @Test("session.title mesaji repository'ye iletilmeli")
    func forwardsSessionTitleToRepository() async throws {
        let repository = SessionTitleRepositoryImpl()
        let handler = SessionTitleMessageHandler(repository: repository)

        let uuid = UUID(uuidString: "11111111-1111-1111-1111-111111111111")!
        let payload = SessionTitleContent(
            sessionId: uuid,
            aiTitle: "iletim testi",
            generatedAt: Date(timeIntervalSince1970: 1_000_000)
        )
        let message = WebSocketBaseMessage(
            type: WebSocketMessageType.sessionTitle.rawValue,
            content: .sessionTitle(payload)
        )

        await handler.handle(message)

        let snapshot = await repository.snapshot()
        #expect(snapshot[uuid.uuidString.lowercased()]?.aiTitle == "iletim testi")
    }

    @Test("Beklenmedik content tipi geldiginde repository degismemeli")
    func ignoresMismatchedContent() async {
        let repository = SessionTitleRepositoryImpl()
        let handler = SessionTitleMessageHandler(repository: repository)

        let message = WebSocketBaseMessage(
            type: WebSocketMessageType.sessionTitle.rawValue,
            content: .text("yanlis tip")
        )

        await handler.handle(message)

        let snapshot = await repository.snapshot()
        #expect(snapshot.isEmpty)
    }
}
