import Foundation
import os

/// Bridge tarafindan gonderilen `subagent.spawned` mesajlarini repository'ye
/// tasiyan handler. WebSocketMessageRouter'a register edilir.
final class SubagentSpawnedHandler: WebSocketMessageHandler {
    private let repository: SubagentRepository
    private let logger = AppLogger.logger(for: "SubagentSpawnedHandler")

    init(repository: SubagentRepository) {
        self.repository = repository
    }

    func handle(_ message: WebSocketBaseMessage) async {
        guard let sessionId = message.metadata?.sessionId else {
            logger.warning("subagent.spawned mesajinda sessionId yok: \(message.id)")
            return
        }
        guard case .subagentSpawned(let content) = message.content else {
            logger.warning("subagent.spawned content beklenen tipte degil: \(message.id)")
            return
        }
        let update = SubagentMapper.toUpdate(spawned: content, sessionId: sessionId)
        await repository.apply(update: update)
    }
}

/// `subagent.progress` mesajlarini repository'ye tasiyan handler.
final class SubagentProgressHandler: WebSocketMessageHandler {
    private let repository: SubagentRepository
    private let logger = AppLogger.logger(for: "SubagentProgressHandler")

    init(repository: SubagentRepository) {
        self.repository = repository
    }

    func handle(_ message: WebSocketBaseMessage) async {
        guard let sessionId = message.metadata?.sessionId else {
            logger.warning("subagent.progress mesajinda sessionId yok: \(message.id)")
            return
        }
        guard case .subagentProgress(let content) = message.content else {
            logger.warning("subagent.progress content beklenen tipte degil: \(message.id)")
            return
        }
        let update = SubagentMapper.toUpdate(progress: content, sessionId: sessionId)
        await repository.apply(update: update)
    }
}

/// `subagent.completed` mesajlarini repository'ye tasiyan handler.
final class SubagentCompletedHandler: WebSocketMessageHandler {
    private let repository: SubagentRepository
    private let logger = AppLogger.logger(for: "SubagentCompletedHandler")

    init(repository: SubagentRepository) {
        self.repository = repository
    }

    func handle(_ message: WebSocketBaseMessage) async {
        guard let sessionId = message.metadata?.sessionId else {
            logger.warning("subagent.completed mesajinda sessionId yok: \(message.id)")
            return
        }
        guard case .subagentCompleted(let content) = message.content else {
            logger.warning("subagent.completed content beklenen tipte degil: \(message.id)")
            return
        }
        let update = SubagentMapper.toUpdate(completed: content, sessionId: sessionId)
        await repository.apply(update: update)
    }
}
