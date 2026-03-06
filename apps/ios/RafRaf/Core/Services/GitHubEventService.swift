import Foundation
import os

/// GitHub webhook event servisi.
/// WebSocket uzerinden gelen github_event mesajlarini tutar ve UI'a bildirir.
@Observable
@MainActor
final class GitHubEventService {
    var recentEvents: [GitHubEventPayload] = []
    var latestEvent: GitHubEventPayload?

    private let logger = AppLogger.logger(for: "GitHubEventService")
    private let maxEvents = 20

    func handleEvent(_ payload: GitHubEventPayload) {
        recentEvents.insert(payload, at: 0)
        if recentEvents.count > maxEvents {
            recentEvents = Array(recentEvents.prefix(maxEvents))
        }
        latestEvent = payload
        logger.info("GitHub event alindi: \(payload.event)/\(payload.action) - \(payload.repo)")
    }

    func clearLatest() {
        latestEvent = nil
    }
}

/// WebSocket handler: github_event mesajlarini GitHubEventService'e iletir.
struct GitHubEventHandler: WebSocketMessageHandler {
    private let service: GitHubEventService

    init(service: GitHubEventService) {
        self.service = service
    }

    func handle(_ message: WebSocketBaseMessage) async {
        guard case .githubEvent(let payload) = message.content else { return }
        await MainActor.run {
            service.handleEvent(payload)
        }
    }
}
