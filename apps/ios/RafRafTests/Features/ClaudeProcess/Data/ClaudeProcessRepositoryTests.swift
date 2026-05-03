import Foundation
import Testing
@testable import RafRaf

/// V1.x SLIM (Item 11) — Claude subprocess supervisor repository + handler testleri.
///
/// Spec: `shared/feature-specs/V1x-claude-supervisor.md` §7.3 (≥4 cases iOS).
/// Kapsanan:
///   1. Spawned handler in-memory state'e yeni process ekler.
///   2. Healthcheck handler state'i mutate eder.
///   3. Stalled handler banner stream'ine `stale` yayinlar.
///   4. Crashed handler banner stream'ine `crashed` + exit code yayinlar.
///   5. Recovered handler 3s sonra otomatik dismiss eder.
///   6. requestRetry retry envelope'unu WebSocket'a yazar.
@Suite("ClaudeProcessRepository tests")
struct ClaudeProcessRepositoryTests {

    private static let now = Date(timeIntervalSince1970: 1_700_000_000)

    private func makeMessage(
        type: WebSocketMessageType,
        content: WebSocketContent
    ) -> WebSocketBaseMessage {
        WebSocketBaseMessage(
            id: "msg-1",
            type: type.rawValue,
            content: content,
            metadata: WebSocketMessageMetadata(sessionId: "sess-1"),
            attachments: nil
        )
    }

    @Test("Spawned handler repository'ye process ekler")
    func spawnedHandlerAddsProcess() async {
        let repo = ClaudeProcessRepositoryImpl()
        let handler = ClaudeProcessSpawnedHandler(repository: repo)
        let dto = ClaudeProcessSpawnedDTO(
            sessionId: "sess-1",
            pid: 12345,
            startedAt: Self.now,
            model: "claude-sonnet-4-7",
            args: nil,
            permissionMode: nil,
            projectDir: nil
        )
        let message = makeMessage(type: .claudeProcessSpawned, content: .claudeProcessSpawned(dto))
        await handler.handle(message)
        let process = await repo.currentProcess(sessionId: "sess-1")
        #expect(process != nil)
        #expect(process?.pid == 12345)
        #expect(process?.state == .starting)
    }

    @Test("Healthcheck handler state'i gunceller")
    func healthcheckHandlerUpdatesState() async {
        let repo = ClaudeProcessRepositoryImpl()
        await repo.applySpawned(
            sessionId: "sess-1", pid: 1, startedAt: Self.now,
            model: "claude-sonnet-4-7", projectDir: nil
        )
        let handler = ClaudeProcessHealthcheckHandler(repository: repo)
        let dto = ClaudeProcessHealthcheckDTO(
            sessionId: "sess-1", pid: 1, status: "running",
            lastStdoutAgeMs: 100, currentTokens: 0, memoryRssKb: 1000,
            cpuPercent1s: 0.0, observedAt: Self.now.addingTimeInterval(5),
            rateLimitResetsAt: nil
        )
        let message = makeMessage(type: .claudeProcessHealthcheck, content: .claudeProcessHealthcheck(dto))
        await handler.handle(message)
        let process = await repo.currentProcess(sessionId: "sess-1")
        #expect(process?.state == .running)
    }

    @Test("Stalled handler banner stream'ine stale yayinlar")
    func stalledHandlerEmitsBanner() async {
        let repo = ClaudeProcessRepositoryImpl()
        await repo.applySpawned(
            sessionId: "sess-1", pid: 1, startedAt: Self.now,
            model: "claude-sonnet-4-7", projectDir: nil
        )
        let handler = ClaudeProcessStalledHandler(repository: repo)
        let dto = ClaudeProcessStalledDTO(
            sessionId: "sess-1", pid: 1,
            lastActivityAt: Self.now.addingTimeInterval(-90),
            staleForMs: 90_000,
            stderrTail: "connection reset",
            stderrTailTruncated: false,
            selfHealPending: true
        )
        let message = makeMessage(type: .claudeProcessStalled, content: .claudeProcessStalled(dto))
        await handler.handle(message)

        // Banner snapshot okuma — stream first yield mevcut snapshot.
        let stream = await repo.observeBanner(sessionId: "sess-1")
        var iterator = stream.makeAsyncIterator()
        let banner = await iterator.next()
        #expect(banner != nil)
        #expect(banner??.state == .stale)
        #expect(banner??.detail == "connection reset")
    }

    @Test("Crashed handler banner stream'ine crashed + exit code yayinlar")
    func crashedHandlerEmitsBannerWithExitCode() async {
        let repo = ClaudeProcessRepositoryImpl()
        await repo.applySpawned(
            sessionId: "sess-1", pid: 1, startedAt: Self.now,
            model: "claude-sonnet-4-7", projectDir: nil
        )
        let handler = ClaudeProcessCrashedHandler(repository: repo)
        let dto = ClaudeProcessCrashedDTO(
            sessionId: "sess-1", pid: 1, exitCode: 137, signal: "SIGKILL",
            stderrTail: "OOM",
            durationMs: 5_000,
            crashedAt: Self.now.addingTimeInterval(60)
        )
        let message = makeMessage(type: .claudeProcessCrashed, content: .claudeProcessCrashed(dto))
        await handler.handle(message)

        let stream = await repo.observeBanner(sessionId: "sess-1")
        var iterator = stream.makeAsyncIterator()
        let banner = await iterator.next()
        #expect(banner??.state == .crashed)
        #expect(banner??.exitCode == 137)
    }

    @Test("Diagnosed handler diagnosis text saklanir")
    func diagnosedHandlerStoresText() async {
        let repo = ClaudeProcessRepositoryImpl()
        await repo.applySpawned(
            sessionId: "sess-1", pid: 1, startedAt: Self.now,
            model: "claude-sonnet-4-7", projectDir: nil
        )
        let handler = ClaudeProcessDiagnosedHandler(repository: repo)
        let dto = ClaudeProcessDiagnosedDTO(
            sessionId: "sess-1",
            diagnosisText: "Subprocess hung on tool_result parser deadlock.",
            recommendedAction: "retry",
            diagnosticTokensUsed: 312,
            diagnosticDurationMs: 4820,
            diagnosedAt: Self.now.addingTimeInterval(95)
        )
        let message = makeMessage(type: .claudeProcessDiagnosed, content: .claudeProcessDiagnosed(dto))
        await handler.handle(message)

        let process = await repo.currentProcess(sessionId: "sess-1")
        #expect(process?.state == .diagnosing)
        #expect(process?.diagnosisText?.hasPrefix("Subprocess hung") == true)
        #expect(process?.recommendedAction == "retry")
    }

    @Test("Recovered handler banner'i 3.2s icinde otomatik kapatir")
    func recoveredHandlerAutoDismisses() async throws {
        let repo = ClaudeProcessRepositoryImpl()
        await repo.applySpawned(
            sessionId: "sess-1", pid: 1, startedAt: Self.now,
            model: "claude-sonnet-4-7", projectDir: nil
        )
        let handler = ClaudeProcessRecoveredHandler(repository: repo)
        let dto = ClaudeProcessRecoveredDTO(
            oldSessionId: "sess-1", newSessionId: "sess-1",
            recoveryReason: "stdout_resumed",
            recoveredAt: Self.now.addingTimeInterval(120)
        )
        let message = makeMessage(type: .claudeProcessRecovered, content: .claudeProcessRecovered(dto))
        await handler.handle(message)

        // Hemen banner gorunur (recovered)
        let process1 = await repo.currentProcess(sessionId: "sess-1")
        #expect(process1?.state == .recovered)

        // 3.2s bekle — auto-dismiss task tamamlanmali
        try await Task.sleep(for: .seconds(3.2))

        let stream = await repo.observeBanner(sessionId: "sess-1")
        var iterator = stream.makeAsyncIterator()
        let banner = await iterator.next()
        // Auto-dismiss sonrasi banner nil olmali (process state hala recovered
        // ama bannerDismissed bayragi true → snapshot nil yayar)
        #expect(banner == .some(nil))
    }

    @Test("Spawn gormeden gelen healthcheck sessizce yoksayilir")
    func healthcheckWithoutSpawnIsIgnored() async {
        let repo = ClaudeProcessRepositoryImpl()
        let handler = ClaudeProcessHealthcheckHandler(repository: repo)
        let dto = ClaudeProcessHealthcheckDTO(
            sessionId: "ghost", pid: 99, status: "running",
            lastStdoutAgeMs: 0, currentTokens: 0, memoryRssKb: 0,
            cpuPercent1s: 0.0, observedAt: Self.now,
            rateLimitResetsAt: nil
        )
        let message = WebSocketBaseMessage(
            id: "msg-1",
            type: WebSocketMessageType.claudeProcessHealthcheck.rawValue,
            content: .claudeProcessHealthcheck(dto),
            metadata: WebSocketMessageMetadata(sessionId: "ghost")
        )
        await handler.handle(message)
        let process = await repo.currentProcess(sessionId: "ghost")
        #expect(process == nil)
    }
}
