import Foundation
import Testing
@testable import RafRaf

/// SubagentLiveActivityCoordinator testleri (T3.1).
///
/// Coordinator, subagent.spawned/completed olaylarini Live Activity
/// guncellemelerine cevirir. Pure logic — gercek ActivityKit cagrilmaz,
/// MockLiveActivityManager kullanilir.
@Suite("SubagentLiveActivityCoordinator Tests")
@MainActor
struct SubagentLiveActivityCoordinatorTests {

    // MARK: - Helpers

    private func makeSubagent(
        id: String,
        status: SubagentStatus,
        sessionId: String = "sess-1",
        spawnedAt: TimeInterval = 0
    ) -> Subagent {
        Subagent(
            id: id,
            sessionId: sessionId,
            parentTaskId: nil,
            name: "agent-\(id)",
            description: nil,
            promptPreview: "do-\(id)",
            subagentType: nil,
            isolation: nil,
            status: status,
            summary: nil,
            totalTokens: nil,
            toolUses: nil,
            durationMs: nil,
            activity: nil,
            spawnedAt: Date(timeIntervalSince1970: spawnedAt),
            updatedAt: nil,
            completedAt: nil
        )
    }

    private func makeCoordinator(
        manager: MockLiveActivityManager? = nil,
        autoDismissDelay: Duration = .milliseconds(50)
    ) -> (SubagentLiveActivityCoordinator, MockLiveActivityManager) {
        let m = manager ?? MockLiveActivityManager()
        let c = SubagentLiveActivityCoordinator(
            manager: m,
            autoDismissDelay: autoDismissDelay,
            activityIdProvider: { "fixed-task-id" }
        )
        return (c, m)
    }

    // MARK: - Pure helpers

    @Test("dominantStatus failed > inProgress > spawned > completed")
    func dominantStatus_priority() {
        let subs = [
            makeSubagent(id: "a", status: .completed),
            makeSubagent(id: "b", status: .spawned),
            makeSubagent(id: "c", status: .inProgress),
            makeSubagent(id: "d", status: .failed)
        ]
        #expect(SubagentLiveActivityCoordinator.resolveDominantStatus(in: subs) == .failed)
    }

    @Test("dominantStatus tum completed ise completed doner")
    func dominantStatus_allCompleted() {
        let subs = [
            makeSubagent(id: "a", status: .completed),
            makeSubagent(id: "b", status: .completed)
        ]
        #expect(SubagentLiveActivityCoordinator.resolveDominantStatus(in: subs) == .completed)
    }

    @Test("dominantStatus bos liste icin nil")
    func dominantStatus_empty() {
        #expect(SubagentLiveActivityCoordinator.resolveDominantStatus(in: []) == nil)
    }

    @Test("phaseIcon her status icin uygun ikon doner")
    func phaseIcon_mapping() {
        #expect(SubagentLiveActivityCoordinator.phaseIcon(for: .completed) == "checkmark.seal.fill")
        #expect(SubagentLiveActivityCoordinator.phaseIcon(for: .failed) == "exclamationmark.triangle.fill")
        #expect(SubagentLiveActivityCoordinator.phaseIcon(for: .inProgress) == "person.2.gobackward")
        #expect(SubagentLiveActivityCoordinator.phaseIcon(for: .spawned) == "person.2.gobackward")
        #expect(SubagentLiveActivityCoordinator.phaseIcon(for: nil) == "circle")
    }

    @Test("progress hesabi: completed / (active + completed)")
    func progress_calc() {
        #expect(SubagentLiveActivityCoordinator.progress(active: 0, completed: 0) == 0)
        #expect(SubagentLiveActivityCoordinator.progress(active: 1, completed: 1) == 0.5)
        #expect(SubagentLiveActivityCoordinator.progress(active: 0, completed: 4) == 1.0)
        #expect(SubagentLiveActivityCoordinator.progress(active: 3, completed: 0) == 0)
    }

    // MARK: - Activity start

    @Test("Ilk spawn'da Live Activity baslar")
    func ingest_firstSpawn_startsActivity() async {
        let (coordinator, manager) = makeCoordinator()
        let snapshot = [makeSubagent(id: "a", status: .spawned)]

        await coordinator.ingest(snapshot: snapshot)

        #expect(manager.startCallCount == 1)
        #expect(coordinator.trackedActivityTaskId == "fixed-task-id")
        #expect(coordinator.trackedSessionId == "sess-1")
    }

    @Test("Ikinci spawn'da Activity update edilir, yeniden start olmaz")
    func ingest_secondSpawn_updates_notStartsAgain() async {
        let (coordinator, manager) = makeCoordinator()
        await coordinator.ingest(snapshot: [makeSubagent(id: "a", status: .spawned)])
        await coordinator.ingest(snapshot: [
            makeSubagent(id: "a", status: .inProgress),
            makeSubagent(id: "b", status: .spawned)
        ])

        #expect(manager.startCallCount == 1)
        #expect(manager.updateCallCount >= 2)
        #expect(coordinator.lastActiveCount == 2)
    }

    // MARK: - Multi-subagent scenario

    @Test("3 subagent spawned ise Activity total=3 ile update edilir")
    func multipleSubagents_updateState() async {
        let (coordinator, manager) = makeCoordinator()
        let snapshot = [
            makeSubagent(id: "a", status: .spawned),
            makeSubagent(id: "b", status: .inProgress),
            makeSubagent(id: "c", status: .spawned)
        ]
        await coordinator.ingest(snapshot: snapshot)

        let state = manager.stateForTask("fixed-task-id")
        #expect(state?.totalSteps == 3)
        #expect(state?.completedSteps == 0)
        #expect(coordinator.lastActiveCount == 3)
    }

    // MARK: - Auto dismiss

    @Test("Tum subagent'lar tamamlandiginda autoDismissDelay sonrasi dismiss")
    func allCompleted_triggersDismissAfterDelay() async {
        let manager = MockLiveActivityManager()
        let (coordinator, _) = makeCoordinator(
            manager: manager,
            autoDismissDelay: .milliseconds(50)
        )

        await coordinator.ingest(snapshot: [makeSubagent(id: "a", status: .spawned)])
        // Tamamlandi
        await coordinator.ingest(snapshot: [makeSubagent(id: "a", status: .completed)])

        // Pending dismiss task'i bekleyecek
        try? await Task.sleep(for: .milliseconds(150))

        #expect(manager.endCallCount == 1)
        #expect(coordinator.trackedActivityTaskId == nil)
    }

    @Test("Pending dismiss yeni spawn ile iptal edilir")
    func pendingDismiss_cancelledByNewSpawn() async {
        let manager = MockLiveActivityManager()
        let (coordinator, _) = makeCoordinator(
            manager: manager,
            autoDismissDelay: .milliseconds(80)
        )

        await coordinator.ingest(snapshot: [makeSubagent(id: "a", status: .spawned)])
        await coordinator.ingest(snapshot: [makeSubagent(id: "a", status: .completed)])

        try? await Task.sleep(for: .milliseconds(20))
        await coordinator.ingest(snapshot: [
            makeSubagent(id: "a", status: .completed),
            makeSubagent(id: "b", status: .spawned, spawnedAt: 1)
        ])

        try? await Task.sleep(for: .milliseconds(150))

        #expect(manager.endCallCount == 0)
        #expect(coordinator.trackedActivityTaskId == "fixed-task-id")
    }

    // MARK: - Manual dismiss

    @Test("dismissNow Activity'yi hemen sonlandirir ve tracking'i temizler")
    func dismissNow_endsActivity_andResets() async {
        let (coordinator, manager) = makeCoordinator()
        await coordinator.ingest(snapshot: [makeSubagent(id: "a", status: .spawned)])
        await coordinator.dismissNow()

        #expect(manager.endCallCount == 1)
        #expect(coordinator.trackedActivityTaskId == nil)
        #expect(coordinator.trackedSessionId == nil)
    }

    // MARK: - Empty snapshot

    @Test("Bos snapshot Activity baslatmaz")
    func emptySnapshot_noOp() async {
        let (coordinator, manager) = makeCoordinator()
        await coordinator.ingest(snapshot: [])
        #expect(manager.startCallCount == 0)
        #expect(coordinator.trackedActivityTaskId == nil)
    }

    // MARK: - Session lock-in

    @Test("Coordinator ilk session'a kilitlenir, baska session'i ignore eder")
    func sessionLockIn() async {
        let (coordinator, manager) = makeCoordinator()
        await coordinator.ingest(snapshot: [
            makeSubagent(id: "a", status: .spawned, sessionId: "sess-A")
        ])
        await coordinator.ingest(snapshot: [
            makeSubagent(id: "a", status: .spawned, sessionId: "sess-A"),
            makeSubagent(id: "x", status: .spawned, sessionId: "sess-B")
        ])
        #expect(coordinator.trackedSessionId == "sess-A")
        // Update sadece sess-A icindeki tek subagent'i sayar (sess-B ignore).
        let state = manager.stateForTask("fixed-task-id")
        #expect(state?.totalSteps == 1)
    }
}
