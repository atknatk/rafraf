import Foundation
import Testing
@testable import RafRaf

/// SubagentRepositoryImpl testleri (T1.7).
/// Spawn -> progress -> completed siralamasinin in-place merge yapildigini,
/// AsyncStream subscriber'larina dogru snapshot'larin yayildigini ve
/// session izolasyonunun korundugunu dogrular.
@Suite("Subagent Repository Impl Tests")
struct SubagentRepositoryImplTests {

    // MARK: - Helpers

    private func makeSubagent(
        id: String,
        sessionId: String = "sess-1",
        parentTaskId: String? = nil,
        status: SubagentStatus = .spawned,
        spawnedAt: Date = Date(timeIntervalSince1970: 1_700_000_000)
    ) -> Subagent {
        Subagent(
            id: id,
            sessionId: sessionId,
            parentTaskId: parentTaskId,
            name: "agent-\(id)",
            description: nil,
            promptPreview: "preview-\(id)",
            subagentType: "general-purpose",
            isolation: nil,
            status: status,
            summary: nil,
            totalTokens: nil,
            toolUses: nil,
            durationMs: nil,
            activity: nil,
            spawnedAt: spawnedAt,
            updatedAt: nil,
            completedAt: nil
        )
    }

    // MARK: - Spawn

    @Test("spawn ile yeni subagent state'e eklenmeli")
    func spawnAddsSubagent() async {
        let repo = SubagentRepositoryImpl()
        let sub = makeSubagent(id: "task-1")

        await repo.apply(update: .spawn(sub))

        let snapshot = await repo.currentSubagents(sessionId: "sess-1")
        #expect(snapshot.count == 1)
        #expect(snapshot[0].id == "task-1")
        #expect(snapshot[0].status == .spawned)
    }

    @Test("ayni id ile ikinci spawn mevcut yasam dongusu durumunu korumali")
    func spawnIdempotentForExisting() async {
        let repo = SubagentRepositoryImpl()
        let initial = makeSubagent(id: "task-1", status: .spawned)
        await repo.apply(update: .spawn(initial))

        // Subagent ilerlemis olsun
        await repo.apply(update: .progress(
            taskId: "task-1",
            sessionId: "sess-1",
            status: .inProgress,
            activity: "running",
            updatedAt: Date()
        ))

        // Yeniden spawn — status reset OLMAMALI
        let again = makeSubagent(id: "task-1", status: .spawned)
        await repo.apply(update: .spawn(again))

        let snapshot = await repo.currentSubagents(sessionId: "sess-1")
        #expect(snapshot.count == 1)
        #expect(snapshot[0].status == .inProgress)
        #expect(snapshot[0].activity == "running")
    }

    // MARK: - Progress

    @Test("progress mevcut subagent'i in-place gunceller")
    func progressUpdatesExisting() async {
        let repo = SubagentRepositoryImpl()
        await repo.apply(update: .spawn(makeSubagent(id: "task-1")))

        let progressTime = Date(timeIntervalSince1970: 1_700_000_100)
        await repo.apply(update: .progress(
            taskId: "task-1",
            sessionId: "sess-1",
            status: .inProgress,
            activity: "compiling",
            updatedAt: progressTime
        ))

        let snapshot = await repo.currentSubagents(sessionId: "sess-1")
        #expect(snapshot[0].status == .inProgress)
        #expect(snapshot[0].activity == "compiling")
        #expect(snapshot[0].updatedAt == progressTime)
    }

    @Test("progress bilinmeyen task icin sessizce yoksayilir")
    func progressIgnoresUnknownTask() async {
        let repo = SubagentRepositoryImpl()
        await repo.apply(update: .progress(
            taskId: "unknown",
            sessionId: "sess-1",
            status: .inProgress,
            activity: "x",
            updatedAt: Date()
        ))
        let snapshot = await repo.currentSubagents(sessionId: "sess-1")
        #expect(snapshot.isEmpty)
    }

    // MARK: - Completed

    @Test("completed subagent state'ini final degerlere ayarlar")
    func completedFinalizesSubagent() async {
        let repo = SubagentRepositoryImpl()
        await repo.apply(update: .spawn(makeSubagent(id: "task-1")))

        let completedAt = Date(timeIntervalSince1970: 1_700_000_300)
        await repo.apply(update: .completed(
            taskId: "task-1",
            sessionId: "sess-1",
            status: .completed,
            summary: "ok",
            totalTokens: 9876,
            toolUses: 4,
            durationMs: 12_500,
            completedAt: completedAt
        ))

        let snapshot = await repo.currentSubagents(sessionId: "sess-1")
        #expect(snapshot[0].status == .completed)
        #expect(snapshot[0].summary == "ok")
        #expect(snapshot[0].totalTokens == 9876)
        #expect(snapshot[0].toolUses == 4)
        #expect(snapshot[0].durationMs == 12_500)
        #expect(snapshot[0].completedAt == completedAt)
        #expect(snapshot[0].updatedAt == completedAt)
    }

    @Test("spawn -> progress -> completed sirasi tum alanlari birlestirmeli")
    func fullLifecycleSequence() async {
        let repo = SubagentRepositoryImpl()
        let baseTime = Date(timeIntervalSince1970: 1_700_000_000)
        await repo.apply(update: .spawn(makeSubagent(id: "task-1", spawnedAt: baseTime)))
        await repo.apply(update: .progress(
            taskId: "task-1",
            sessionId: "sess-1",
            status: .inProgress,
            activity: "phase 1",
            updatedAt: baseTime.addingTimeInterval(10)
        ))
        await repo.apply(update: .completed(
            taskId: "task-1",
            sessionId: "sess-1",
            status: .completed,
            summary: "done",
            totalTokens: 100,
            toolUses: 1,
            durationMs: 30_000,
            completedAt: baseTime.addingTimeInterval(30)
        ))

        let snapshot = await repo.currentSubagents(sessionId: "sess-1")
        #expect(snapshot.count == 1)
        #expect(snapshot[0].spawnedAt == baseTime)
        #expect(snapshot[0].status == .completed)
        #expect(snapshot[0].summary == "done")
        #expect(snapshot[0].activity == "phase 1") // progress'ten gelen aktivite korunur
        #expect(snapshot[0].durationMs == 30_000)
    }

    // MARK: - Session Isolation

    @Test("farkli session'lar birbirinden izole olmali")
    func sessionIsolation() async {
        let repo = SubagentRepositoryImpl()
        await repo.apply(update: .spawn(makeSubagent(id: "a", sessionId: "s1")))
        await repo.apply(update: .spawn(makeSubagent(id: "b", sessionId: "s2")))

        let s1 = await repo.currentSubagents(sessionId: "s1")
        let s2 = await repo.currentSubagents(sessionId: "s2")
        #expect(s1.count == 1)
        #expect(s2.count == 1)
        #expect(s1[0].id == "a")
        #expect(s2[0].id == "b")
    }

    @Test("currentAllSubagents tum oturumlari birlestirmeli")
    func allSubagentsAggregation() async {
        let repo = SubagentRepositoryImpl()
        await repo.apply(update: .spawn(makeSubagent(
            id: "a",
            sessionId: "s1",
            spawnedAt: Date(timeIntervalSince1970: 100)
        )))
        await repo.apply(update: .spawn(makeSubagent(
            id: "b",
            sessionId: "s2",
            spawnedAt: Date(timeIntervalSince1970: 200)
        )))
        let all = await repo.currentAllSubagents()
        #expect(all.count == 2)
        // spawnedAt artan sirada
        #expect(all.first?.id == "a")
        #expect(all.last?.id == "b")
    }

    // MARK: - Sorting

    @Test("snapshot spawnedAt artan sirada donulmeli")
    func snapshotSortedBySpawnedAt() async {
        let repo = SubagentRepositoryImpl()
        await repo.apply(update: .spawn(makeSubagent(
            id: "later",
            spawnedAt: Date(timeIntervalSince1970: 200)
        )))
        await repo.apply(update: .spawn(makeSubagent(
            id: "earlier",
            spawnedAt: Date(timeIntervalSince1970: 100)
        )))
        let snapshot = await repo.currentSubagents(sessionId: "sess-1")
        #expect(snapshot.map(\.id) == ["earlier", "later"])
    }

    // MARK: - Clear

    @Test("clear bir session'a ait state'i sifirlar")
    func clearWipesSession() async {
        let repo = SubagentRepositoryImpl()
        await repo.apply(update: .spawn(makeSubagent(id: "a", sessionId: "s1")))
        await repo.apply(update: .spawn(makeSubagent(id: "b", sessionId: "s2")))

        await repo.clear(sessionId: "s1")

        let s1 = await repo.currentSubagents(sessionId: "s1")
        let s2 = await repo.currentSubagents(sessionId: "s2")
        #expect(s1.isEmpty)
        #expect(s2.count == 1)
    }

    // MARK: - Streaming

    @Test("observeSubagents subscribe aninda mevcut snapshot'i yayar")
    func observeYieldsInitialSnapshot() async {
        let repo = SubagentRepositoryImpl()
        await repo.apply(update: .spawn(makeSubagent(id: "a")))
        let stream = await repo.observeSubagents(sessionId: "sess-1")
        var iterator = stream.makeAsyncIterator()
        let first = await iterator.next()
        #expect(first?.count == 1)
        #expect(first?[0].id == "a")
    }

    @Test("observeSubagents her degisiklikte yeni snapshot yayar")
    func observeYieldsOnUpdate() async {
        let repo = SubagentRepositoryImpl()
        let stream = await repo.observeSubagents(sessionId: "sess-1")
        var iterator = stream.makeAsyncIterator()

        // initial empty snapshot
        let initial = await iterator.next()
        #expect(initial?.isEmpty == true)

        await repo.apply(update: .spawn(makeSubagent(id: "a")))
        let afterSpawn = await iterator.next()
        #expect(afterSpawn?.count == 1)
        #expect(afterSpawn?[0].status == .spawned)

        await repo.apply(update: .progress(
            taskId: "a",
            sessionId: "sess-1",
            status: .inProgress,
            activity: "x",
            updatedAt: Date()
        ))
        let afterProgress = await iterator.next()
        #expect(afterProgress?[0].status == .inProgress)
    }
}
