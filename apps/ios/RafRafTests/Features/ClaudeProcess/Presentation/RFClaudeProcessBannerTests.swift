import Foundation
import Testing
@testable import RafRaf

/// V1.x SLIM (Item 11) — Banner state machine projeksiyon testleri.
///
/// `RFClaudeProcessBanner` gercek SwiftUI render'i ViewInspector / Snapshot
/// gibi bir bagimliliga ihtiyac duyar. Bu test dosyasi banner'in *anlam*
/// dogrulugunu (`ClaudeProcessBannerState.isVisible`, repository → banner
/// projeksiyonu) iddialarla kanitlar. UI rendering davranisi #Preview ile
/// gozle dogrulanir.
///
/// Spec §3 — banner state machine: stale/diagnosing/rate_limited/crashed/
/// recovered → gorunur; running/idle/completed/starting → gizli.
@Suite("RFClaudeProcessBanner state tests")
struct RFClaudeProcessBannerTests {

    private static let now = Date(timeIntervalSince1970: 1_700_000_000)

    // MARK: - Visibility coverage (6 visible + 4 hidden = 9 case)

    @Test("Banner gizli durumlar (running/idle/completed/starting)")
    func hiddenStates() {
        for state: ClaudeProcessState in [.running, .idle, .completed, .starting] {
            let banner = ClaudeProcessBannerState(sessionId: "s", state: state)
            #expect(!banner.isVisible, "state \(state) banner gizli olmali")
        }
    }

    @Test("Banner gorunur durumlar (stale/diagnosing/rateLimited/crashed/recovered)")
    func visibleStates() {
        for state: ClaudeProcessState in [.stale, .diagnosing, .rateLimited, .crashed, .recovered] {
            let banner = ClaudeProcessBannerState(sessionId: "s", state: state)
            #expect(banner.isVisible, "state \(state) banner gorunur olmali")
        }
    }

    // MARK: - Repository projeksiyonu

    @Test("Repository spawned -> banner gizli")
    func spawnedDoesNotShowBanner() async {
        let repo = ClaudeProcessRepositoryImpl()
        await repo.applySpawned(
            sessionId: "s1", pid: 1, startedAt: Self.now,
            model: "claude-sonnet-4-7", projectDir: nil
        )
        let stream = await repo.observeBanner(sessionId: "s1")
        var iterator = stream.makeAsyncIterator()
        let banner = await iterator.next()
        #expect(banner == .some(nil), "starting state banner gizli olmali")
    }

    @Test("Repository stalled -> banner stale gorunur, detail stderr_tail")
    func stalledShowsBanner() async {
        let repo = ClaudeProcessRepositoryImpl()
        await repo.applySpawned(
            sessionId: "s1", pid: 1, startedAt: Self.now,
            model: "claude-sonnet-4-7", projectDir: nil
        )
        await repo.applyStalled(
            sessionId: "s1", stderrTail: "boom",
            observedAt: Self.now.addingTimeInterval(90)
        )
        let stream = await repo.observeBanner(sessionId: "s1")
        var iterator = stream.makeAsyncIterator()
        let banner = await iterator.next()
        #expect(banner??.state == .stale)
        #expect(banner??.detail == "boom")
    }

    @Test("Repository diagnosed -> banner diagnosing, detail diagnosis_text")
    func diagnosedShowsBanner() async {
        let repo = ClaudeProcessRepositoryImpl()
        await repo.applySpawned(
            sessionId: "s1", pid: 1, startedAt: Self.now,
            model: "claude-sonnet-4-7", projectDir: nil
        )
        await repo.applyDiagnosed(
            sessionId: "s1", diagnosisText: "transient parser deadlock",
            recommendedAction: "retry",
            observedAt: Self.now.addingTimeInterval(95)
        )
        let stream = await repo.observeBanner(sessionId: "s1")
        var iterator = stream.makeAsyncIterator()
        let banner = await iterator.next()
        #expect(banner??.state == .diagnosing)
        #expect(banner??.detail == "transient parser deadlock")
    }

    @Test("Repository crashed -> banner crashed, exitCode + signal saklanir")
    func crashedShowsBannerWithExitCode() async {
        let repo = ClaudeProcessRepositoryImpl()
        await repo.applySpawned(
            sessionId: "s1", pid: 1, startedAt: Self.now,
            model: "claude-sonnet-4-7", projectDir: nil
        )
        await repo.applyCrashed(
            sessionId: "s1", exitCode: 137, signal: "SIGKILL",
            stderrTail: "OOM",
            observedAt: Self.now.addingTimeInterval(60)
        )
        let stream = await repo.observeBanner(sessionId: "s1")
        var iterator = stream.makeAsyncIterator()
        let banner = await iterator.next()
        #expect(banner??.state == .crashed)
        #expect(banner??.exitCode == 137)
    }

    @Test("Repository recovered -> banner recovered (auto-dismiss async)")
    func recoveredShowsBanner() async {
        let repo = ClaudeProcessRepositoryImpl()
        await repo.applySpawned(
            sessionId: "s1", pid: 1, startedAt: Self.now,
            model: "claude-sonnet-4-7", projectDir: nil
        )
        await repo.applyRecovered(
            sessionId: "s1",
            observedAt: Self.now.addingTimeInterval(120)
        )
        // Hemen state recovered (auto-dismiss 3s sonra)
        let process = await repo.currentProcess(sessionId: "s1")
        #expect(process?.state == .recovered)
    }

    @Test("Kullanici dismissBanner cagirir -> stream nil yayinlar")
    func dismissBannerReturnsNil() async {
        let repo = ClaudeProcessRepositoryImpl()
        await repo.applySpawned(
            sessionId: "s1", pid: 1, startedAt: Self.now,
            model: "claude-sonnet-4-7", projectDir: nil
        )
        await repo.applyStalled(
            sessionId: "s1", stderrTail: "x",
            observedAt: Self.now.addingTimeInterval(90)
        )
        await repo.dismissBanner(sessionId: "s1")
        let stream = await repo.observeBanner(sessionId: "s1")
        var iterator = stream.makeAsyncIterator()
        let banner = await iterator.next()
        #expect(banner == .some(nil))
    }
}
