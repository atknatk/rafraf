import Foundation
import os

/// `session.title` WebSocket mesajlarini repository'ye yonlendiren handler.
///
/// `WebSocketMessageRouter` bu handler'i `WebSocketMessageType.sessionTitle`
/// rawValue'su altinda cagirir; payload `SessionTitleContent` ise
/// `SessionTitleRepositoryImpl.handle(content:)` ile yayilir.
///
/// T1.6'da konulan TODO branch (router log-only) bu handler kaydiyla yerini
/// gercek isleme birakir.
final class SessionTitleMessageHandler: WebSocketMessageHandler {
    private let repository: SessionTitleRepositoryImpl
    private let logger = Logger(
        subsystem: "com.rafraf",
        category: "SessionTitleMessageHandler"
    )

    init(repository: SessionTitleRepositoryImpl) {
        self.repository = repository
    }

    func handle(_ message: WebSocketBaseMessage) async {
        guard case .sessionTitle(let payload) = message.content else {
            logger.warning(
                "session.title mesaji bekleniyor ama farkli content tipi geldi: \(String(describing: message.content), privacy: .public)"
            )
            return
        }
        await repository.handle(content: payload)
    }
}
