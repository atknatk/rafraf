import Foundation
import os

/// V1.x SLIM (Item 11) — Bridge → backend → iOS Claude subprocess supervisor
/// envelope handler'lari.
///
/// Spec: `shared/feature-specs/V1x-claude-supervisor.md` §4.
/// Tum handler'lar `WebSocketMessageRouter`'a `ContentView` task'inde register
/// edilir (mirror: `registerSubagentHandlers()` patterni).
///
/// Her handler tek bir DTO tipini ClaudeProcessRepository write API'sine
/// projeksiyonlar; mapper rolu burada minimal cunku DTO sema = domain
/// state alanlari neredeyse 1:1.

private let supervisorHandlersLogger = AppLogger.logger(for: "ClaudeProcessHandlers")

/// `event.claude.process.spawned` → repository.applySpawned.
final class ClaudeProcessSpawnedHandler: WebSocketMessageHandler {
    private let repository: ClaudeProcessRepository

    init(repository: ClaudeProcessRepository) {
        self.repository = repository
    }

    func handle(_ message: WebSocketBaseMessage) async {
        guard case .claudeProcessSpawned(let dto) = message.content else {
            supervisorHandlersLogger.warning("spawned content beklenen tipte degil: \(message.id)")
            return
        }
        await repository.applySpawned(
            sessionId: dto.sessionId,
            pid: dto.pid,
            startedAt: dto.startedAt,
            model: dto.model,
            projectDir: dto.projectDir
        )
    }
}

/// `event.claude.process.healthcheck` → repository.applyHealthcheck.
final class ClaudeProcessHealthcheckHandler: WebSocketMessageHandler {
    private let repository: ClaudeProcessRepository

    init(repository: ClaudeProcessRepository) {
        self.repository = repository
    }

    func handle(_ message: WebSocketBaseMessage) async {
        guard case .claudeProcessHealthcheck(let dto) = message.content else {
            supervisorHandlersLogger.warning("healthcheck content beklenen tipte degil: \(message.id)")
            return
        }
        let mapped = ClaudeProcessState.from(rawString: dto.status)
        await repository.applyHealthcheck(
            sessionId: dto.sessionId,
            state: mapped,
            observedAt: dto.observedAt,
            rateLimitResetsAt: dto.rateLimitResetsAt
        )
    }
}

/// `event.claude.process.stalled` → repository.applyStalled.
final class ClaudeProcessStalledHandler: WebSocketMessageHandler {
    private let repository: ClaudeProcessRepository

    init(repository: ClaudeProcessRepository) {
        self.repository = repository
    }

    func handle(_ message: WebSocketBaseMessage) async {
        guard case .claudeProcessStalled(let dto) = message.content else {
            supervisorHandlersLogger.warning("stalled content beklenen tipte degil: \(message.id)")
            return
        }
        await repository.applyStalled(
            sessionId: dto.sessionId,
            stderrTail: dto.stderrTail,
            observedAt: dto.lastActivityAt
        )
    }
}

/// `event.claude.process.crashed` → repository.applyCrashed.
final class ClaudeProcessCrashedHandler: WebSocketMessageHandler {
    private let repository: ClaudeProcessRepository

    init(repository: ClaudeProcessRepository) {
        self.repository = repository
    }

    func handle(_ message: WebSocketBaseMessage) async {
        guard case .claudeProcessCrashed(let dto) = message.content else {
            supervisorHandlersLogger.warning("crashed content beklenen tipte degil: \(message.id)")
            return
        }
        // Spec §4.4 — signal "" clean-but-nonzero. Bos string'i nil'e map et.
        let normalizedSignal: String?
        if let raw = dto.signal, !raw.isEmpty {
            normalizedSignal = raw
        } else {
            normalizedSignal = nil
        }
        await repository.applyCrashed(
            sessionId: dto.sessionId,
            exitCode: dto.exitCode,
            signal: normalizedSignal,
            stderrTail: dto.stderrTail,
            observedAt: dto.crashedAt
        )
    }
}

/// `event.claude.process.recovered` → repository.applyRecovered.
final class ClaudeProcessRecoveredHandler: WebSocketMessageHandler {
    private let repository: ClaudeProcessRepository

    init(repository: ClaudeProcessRepository) {
        self.repository = repository
    }

    func handle(_ message: WebSocketBaseMessage) async {
        guard case .claudeProcessRecovered(let dto) = message.content else {
            supervisorHandlersLogger.warning("recovered content beklenen tipte degil: \(message.id)")
            return
        }
        // Spec §4.5 — old/new sessionId; SLIM: yeni id'yi state anahtari kabul et.
        // Onceki id farkliysa yine de update'i yeni id altina yansit (manual_retry
        // dali). Eger ikisi de ayniysa zaten idempotent.
        await repository.applyRecovered(
            sessionId: dto.newSessionId,
            observedAt: dto.recoveredAt
        )
    }
}

/// V1.x SLIM — DI-friendly handler bundle. ContentView tek bir Factory cagrisi
/// ile alir, app start'inda `WebSocketMessageRouter`'a sirayla register eder.
struct ClaudeProcessMessageHandlerSet: Sendable {
    let spawned: ClaudeProcessSpawnedHandler
    let healthcheck: ClaudeProcessHealthcheckHandler
    let stalled: ClaudeProcessStalledHandler
    let crashed: ClaudeProcessCrashedHandler
    let recovered: ClaudeProcessRecoveredHandler
    let diagnosed: ClaudeProcessDiagnosedHandler
}

/// `event.claude.process.diagnosed` → repository.applyDiagnosed.
final class ClaudeProcessDiagnosedHandler: WebSocketMessageHandler {
    private let repository: ClaudeProcessRepository

    init(repository: ClaudeProcessRepository) {
        self.repository = repository
    }

    func handle(_ message: WebSocketBaseMessage) async {
        guard case .claudeProcessDiagnosed(let dto) = message.content else {
            supervisorHandlersLogger.warning("diagnosed content beklenen tipte degil: \(message.id)")
            return
        }
        await repository.applyDiagnosed(
            sessionId: dto.sessionId,
            diagnosisText: dto.diagnosisText,
            recommendedAction: dto.recommendedAction,
            observedAt: dto.diagnosedAt
        )
    }
}
