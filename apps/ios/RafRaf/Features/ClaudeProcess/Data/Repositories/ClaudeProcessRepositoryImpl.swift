import Foundation
import os

/// V1.x SLIM — Claude subprocess supervisor repository implementasyonu.
///
/// Spec: `shared/feature-specs/V1x-claude-supervisor.md` §7 (slim scope:
/// banner + retry yalnizca; history/detail V1.(x+1)).
///
/// Mimari:
///   - `ProcessState` actor: `[String: SupervisedClaudeProcess]` keyed by sessionID.
///   - Subscriber'lar AsyncStream continuation'larina kayitli; her wire envelope
///     uygulamasinda yeni snapshot yayilir.
///   - Banner stream: process state → ClaudeProcessBannerState projeksiyonu.
///   - `requestRetry` WebSocketClient.send ile spec §4.7 envelope'ini bridge'e iletir.
///
/// Notlar:
///   - Gevsek baglanti: `WebSocketClient` opsiyonel — preview/test no-op.
///   - `notificationFactory` opsiyonel — push bildirimi yan yol; SLIM scope'da
///     stalled/crashed/rate_limited durumlarinda 1x lokal bildirim atar.
final class ClaudeProcessRepositoryImpl: ClaudeProcessRepository, @unchecked Sendable {
    private let state = ProcessState()
    private let logger = AppLogger.logger(for: "ClaudeProcessRepository")
    private let webSocketClient: WebSocketClient?
    private let notificationFactory: ClaudeProcessNotificationFactoryProtocol?

    init(
        webSocketClient: WebSocketClient? = nil,
        notificationFactory: ClaudeProcessNotificationFactoryProtocol? = nil
    ) {
        self.webSocketClient = webSocketClient
        self.notificationFactory = notificationFactory
    }

    // MARK: - Read API

    func observeProcesses(sessionId: String) async -> AsyncStream<SupervisedClaudeProcess?> {
        await state.subscribeProcess(sessionId: sessionId)
    }

    func observeBanner(sessionId: String) async -> AsyncStream<ClaudeProcessBannerState?> {
        await state.subscribeBanner(sessionId: sessionId)
    }

    func currentProcess(sessionId: String) async -> SupervisedClaudeProcess? {
        await state.currentProcess(sessionId: sessionId)
    }

    func dismissBanner(sessionId: String) async {
        await state.dismissBanner(sessionId: sessionId)
        logger.info("Banner dismiss - session: \(sessionId, privacy: .public)")
    }

    // MARK: - Write API (handlers)

    func applySpawned(
        sessionId: String,
        pid: Int,
        startedAt: Date,
        model: String,
        projectDir: String?
    ) async {
        let process = SupervisedClaudeProcess(
            id: sessionId,
            pid: pid,
            state: .starting,
            startedAt: startedAt,
            lastObservedAt: startedAt,
            model: model,
            projectDir: projectDir
        )
        await state.replaceProcess(process)
        logger.info("spawned - session: \(sessionId, privacy: .public), pid: \(pid)")
    }

    func applyHealthcheck(
        sessionId: String,
        state newState: ClaudeProcessState,
        observedAt: Date,
        rateLimitResetsAt: Date?
    ) async {
        await state.mutate(sessionId: sessionId) { process in
            process.state = newState
            process.lastObservedAt = observedAt
            if let resets = rateLimitResetsAt {
                process.rateLimitResetsAt = resets
            }
        }
        // Rate-limited gecisinde 1x bildirim
        if newState == .rateLimited {
            await dispatchNotification(sessionId: sessionId, kind: .rateLimited, detail: nil)
        }
    }

    func applyStalled(
        sessionId: String,
        stderrTail: String,
        observedAt: Date
    ) async {
        await state.mutate(sessionId: sessionId) { process in
            process.state = .stale
            process.lastObservedAt = observedAt
            process.lastStderrTail = stderrTail
        }
        await dispatchNotification(sessionId: sessionId, kind: .stalled, detail: stderrTail)
        logger.warning("stalled - session: \(sessionId, privacy: .public)")
    }

    func applyDiagnosed(
        sessionId: String,
        diagnosisText: String,
        recommendedAction: String,
        observedAt: Date
    ) async {
        await state.mutate(sessionId: sessionId) { process in
            process.state = .diagnosing
            process.lastObservedAt = observedAt
            process.diagnosisText = diagnosisText
            process.recommendedAction = recommendedAction
        }
        logger.info("diagnosed - session: \(sessionId, privacy: .public), action: \(recommendedAction, privacy: .public)")
    }

    func applyCrashed(
        sessionId: String,
        exitCode: Int,
        signal: String?,
        stderrTail: String?,
        observedAt: Date
    ) async {
        await state.mutate(sessionId: sessionId) { process in
            process.state = .crashed
            process.lastObservedAt = observedAt
            process.exitCode = exitCode
            process.signal = signal
            if let tail = stderrTail {
                process.lastStderrTail = tail
            }
        }
        await dispatchNotification(sessionId: sessionId, kind: .crashed, detail: stderrTail)
        logger.error("crashed - session: \(sessionId, privacy: .public), exitCode: \(exitCode)")
    }

    func applyRecovered(
        sessionId: String,
        observedAt: Date
    ) async {
        await state.mutate(sessionId: sessionId) { process in
            process.state = .recovered
            process.lastObservedAt = observedAt
        }
        logger.info("recovered - session: \(sessionId, privacy: .public)")
        // Spec: 3s sonra otomatik dismiss → banner gizlenir.
        Task { [weak self] in
            try? await Task.sleep(for: .seconds(3))
            await self?.state.dismissBanner(sessionId: sessionId)
        }
    }

    // MARK: - Retry

    func requestRetry(sessionId: String) async throws {
        let dto = ClaudeProcessRetryRequestDTO(sessionId: sessionId, userId: nil)
        let message = WebSocketBaseMessage(
            type: WebSocketMessageType.claudeProcessRetry.rawValue,
            content: .claudeProcessRetry(dto),
            metadata: WebSocketMessageMetadata(
                sessionId: sessionId,
                direction: WebSocketMessageDirection.clientToServer.rawValue
            )
        )
        guard let client = webSocketClient else {
            logger.warning("requestRetry: webSocketClient yok (test path)")
            return
        }
        try await client.send(message: message)
        logger.info("retry istegi gonderildi - session: \(sessionId, privacy: .public)")
    }

    // MARK: - Notification side-effect

    private func dispatchNotification(
        sessionId: String,
        kind: ClaudeProcessNotificationKind,
        detail: String?
    ) async {
        guard let factory = notificationFactory else { return }
        await factory.fire(sessionId: sessionId, kind: kind, detail: detail)
    }
}

// MARK: - Internal state actor

/// Process kayitlari + AsyncStream continuation'larini koruyan actor.
private actor ProcessState {
    private var processes: [String: SupervisedClaudeProcess] = [:]
    private var processContinuations: [String: [UUID: AsyncStream<SupervisedClaudeProcess?>.Continuation]] = [:]
    private var bannerContinuations: [String: [UUID: AsyncStream<ClaudeProcessBannerState?>.Continuation]] = [:]
    /// Banner kullanici tarafindan dismiss edildiginde true; sonraki state
    /// degisikligine kadar banner stream nil yayinlar (chat-scoped).
    private var bannerDismissed: [String: Bool] = [:]

    func currentProcess(sessionId: String) -> SupervisedClaudeProcess? {
        processes[sessionId]
    }

    func subscribeProcess(sessionId: String) -> AsyncStream<SupervisedClaudeProcess?> {
        AsyncStream { continuation in
            let id = UUID()
            self.registerProcess(id: id, continuation: continuation, sessionId: sessionId)
            continuation.yield(self.processes[sessionId])
            continuation.onTermination = { @Sendable [weak self] _ in
                guard let self else { return }
                Task { await self.unregisterProcess(id: id, sessionId: sessionId) }
            }
        }
    }

    func subscribeBanner(sessionId: String) -> AsyncStream<ClaudeProcessBannerState?> {
        AsyncStream { continuation in
            let id = UUID()
            self.registerBanner(id: id, continuation: continuation, sessionId: sessionId)
            continuation.yield(self.bannerSnapshot(sessionId: sessionId))
            continuation.onTermination = { @Sendable [weak self] _ in
                guard let self else { return }
                Task { await self.unregisterBanner(id: id, sessionId: sessionId) }
            }
        }
    }

    func replaceProcess(_ process: SupervisedClaudeProcess) {
        processes[process.id] = process
        bannerDismissed[process.id] = false
        yield(sessionId: process.id)
    }

    func mutate(sessionId: String, _ block: (inout SupervisedClaudeProcess) -> Void) {
        guard var process = processes[sessionId] else {
            // Spawn gormeden gelen update — sessizce yoksay (bridge state machine
            // disinda kalan envelope; spec §3 starting → first event).
            return
        }
        block(&process)
        processes[sessionId] = process
        // State degistiyse banner dismiss bayragini sifirla — yeni event yeni
        // bildirim hakkidir.
        bannerDismissed[sessionId] = false
        yield(sessionId: sessionId)
    }

    func dismissBanner(sessionId: String) {
        bannerDismissed[sessionId] = true
        yield(sessionId: sessionId)
    }

    // MARK: - Snapshot helpers

    private func bannerSnapshot(sessionId: String) -> ClaudeProcessBannerState? {
        guard let process = processes[sessionId] else { return nil }
        if bannerDismissed[sessionId] == true { return nil }
        let banner = ClaudeProcessBannerState(
            sessionId: sessionId,
            state: process.state,
            detail: process.diagnosisText ?? process.lastStderrTail,
            exitCode: process.exitCode,
            rateLimitResetsAt: process.rateLimitResetsAt
        )
        return banner.isVisible ? banner : nil
    }

    private func yield(sessionId: String) {
        let process = processes[sessionId]
        if let bucket = processContinuations[sessionId] {
            for cont in bucket.values {
                cont.yield(process)
            }
        }
        let banner = bannerSnapshot(sessionId: sessionId)
        if let bucket = bannerContinuations[sessionId] {
            for cont in bucket.values {
                cont.yield(banner)
            }
        }
    }

    // MARK: - Continuation bookkeeping

    private func registerProcess(
        id: UUID,
        continuation: AsyncStream<SupervisedClaudeProcess?>.Continuation,
        sessionId: String
    ) {
        var bucket = processContinuations[sessionId] ?? [:]
        bucket[id] = continuation
        processContinuations[sessionId] = bucket
    }

    private func unregisterProcess(id: UUID, sessionId: String) {
        guard var bucket = processContinuations[sessionId] else { return }
        bucket.removeValue(forKey: id)
        if bucket.isEmpty {
            processContinuations.removeValue(forKey: sessionId)
        } else {
            processContinuations[sessionId] = bucket
        }
    }

    private func registerBanner(
        id: UUID,
        continuation: AsyncStream<ClaudeProcessBannerState?>.Continuation,
        sessionId: String
    ) {
        var bucket = bannerContinuations[sessionId] ?? [:]
        bucket[id] = continuation
        bannerContinuations[sessionId] = bucket
    }

    private func unregisterBanner(id: UUID, sessionId: String) {
        guard var bucket = bannerContinuations[sessionId] else { return }
        bucket.removeValue(forKey: id)
        if bucket.isEmpty {
            bannerContinuations.removeValue(forKey: sessionId)
        } else {
            bannerContinuations[sessionId] = bucket
        }
    }
}
