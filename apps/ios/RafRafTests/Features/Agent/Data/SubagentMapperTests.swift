import Foundation
import Testing
@testable import RafRaf

/// Subagent mapper testleri (T1.7).
/// `SubagentMapper` Bridge Content struct'larini Domain `SubagentUpdate`
/// modellerine cevirir. Bu test suite mapping'in alan-bazli dogrulugunu
/// guvence altina alir.
@Suite("Subagent Mapper Tests")
struct SubagentMapperTests {

    // MARK: - Spawned

    @Test("spawned content tum alanlari Subagent'a tasinmali")
    func spawnedFullFields() {
        let now = Date(timeIntervalSince1970: 1_700_000_000)
        let content = SubagentSpawnedContent(
            taskId: "task-1",
            name: "developer",
            description: "implement feature X",
            promptPreview: "Add subagent tree to Agent feature",
            subagentType: "general-purpose",
            isolation: "worktree",
            startedAt: now
        )

        let update = SubagentMapper.toUpdate(spawned: content, sessionId: "sess-1")

        guard case .spawn(let subagent) = update else {
            Issue.record("Expected .spawn case")
            return
        }
        #expect(subagent.id == "task-1")
        #expect(subagent.sessionId == "sess-1")
        #expect(subagent.parentTaskId == nil)
        #expect(subagent.name == "developer")
        #expect(subagent.description == "implement feature X")
        #expect(subagent.promptPreview == "Add subagent tree to Agent feature")
        #expect(subagent.subagentType == "general-purpose")
        #expect(subagent.isolation == "worktree")
        #expect(subagent.status == .spawned)
        #expect(subagent.spawnedAt == now)
        #expect(subagent.completedAt == nil)
        #expect(subagent.totalTokens == nil)
    }

    @Test("spawned parentTaskId opsiyonel parametre olarak iletilmeli")
    func spawnedParentTaskId() {
        let content = SubagentSpawnedContent(
            taskId: "child",
            name: "tester",
            description: nil,
            promptPreview: "p",
            subagentType: nil,
            isolation: nil,
            startedAt: Date()
        )
        let update = SubagentMapper.toUpdate(
            spawned: content,
            sessionId: "s",
            parentTaskId: "parent"
        )
        guard case .spawn(let subagent) = update else {
            Issue.record("Expected .spawn case")
            return
        }
        #expect(subagent.parentTaskId == "parent")
    }

    // MARK: - Progress

    @Test("progress content SubagentUpdate.progress yaratmali")
    func progressMapping() {
        let now = Date(timeIntervalSince1970: 1_700_000_100)
        let content = SubagentProgressContent(
            taskId: "task-1",
            status: "in_progress",
            activity: "running tests",
            updatedAt: now
        )
        let update = SubagentMapper.toUpdate(progress: content, sessionId: "sess-1")
        guard case .progress(let taskId, let sessionId, let status, let activity, let updatedAt) = update else {
            Issue.record("Expected .progress case")
            return
        }
        #expect(taskId == "task-1")
        #expect(sessionId == "sess-1")
        #expect(status == .inProgress)
        #expect(activity == "running tests")
        #expect(updatedAt == now)
    }

    @Test("progress bilinmeyen status string'i in_progress'e duser")
    func progressUnknownStatusFallback() {
        let content = SubagentProgressContent(
            taskId: "t",
            status: "weird-status",
            activity: "x",
            updatedAt: Date()
        )
        let update = SubagentMapper.toUpdate(progress: content, sessionId: "s")
        guard case .progress(_, _, let status, _, _) = update else {
            Issue.record("Expected .progress case")
            return
        }
        #expect(status == .inProgress)
    }

    @Test("progress 'running' alternatif status'u in_progress'e mapping")
    func progressRunningAlias() {
        let content = SubagentProgressContent(
            taskId: "t",
            status: "running",
            activity: "x",
            updatedAt: Date()
        )
        let update = SubagentMapper.toUpdate(progress: content, sessionId: "s")
        guard case .progress(_, _, let status, _, _) = update else {
            Issue.record("Expected .progress case")
            return
        }
        #expect(status == .inProgress)
    }

    // MARK: - Completed

    @Test("completed content tum alanlari SubagentUpdate.completed'a tasimali")
    func completedMapping() {
        let now = Date(timeIntervalSince1970: 1_700_000_200)
        let content = SubagentCompletedContent(
            taskId: "task-1",
            status: "completed",
            summary: "All tests pass",
            totalTokens: 1234,
            toolUses: 5,
            durationMs: 7800,
            completedAt: now
        )
        let update = SubagentMapper.toUpdate(completed: content, sessionId: "sess-1")
        guard case .completed(let taskId, let sessionId, let status, let summary, let totalTokens, let toolUses, let durationMs, let completedAt) = update else {
            Issue.record("Expected .completed case")
            return
        }
        #expect(taskId == "task-1")
        #expect(sessionId == "sess-1")
        #expect(status == .completed)
        #expect(summary == "All tests pass")
        #expect(totalTokens == 1234)
        #expect(toolUses == 5)
        #expect(durationMs == 7800)
        #expect(completedAt == now)
    }

    @Test("completed status 'failed' SubagentStatus.failed'a mapping")
    func completedFailedStatus() {
        let content = SubagentCompletedContent(
            taskId: "t",
            status: "failed",
            summary: nil,
            totalTokens: 0,
            toolUses: 0,
            durationMs: 0,
            completedAt: Date()
        )
        let update = SubagentMapper.toUpdate(completed: content, sessionId: "s")
        guard case .completed(_, _, let status, _, _, _, _, _) = update else {
            Issue.record("Expected .completed case")
            return
        }
        #expect(status == .failed)
    }

    // MARK: - SubagentStatus

    @Test("SubagentStatus.from yedek mapping'leri dogru dusurmeli", arguments: [
        ("running", SubagentStatus.inProgress),
        ("active", SubagentStatus.inProgress),
        ("started", SubagentStatus.inProgress),
        ("done", SubagentStatus.completed),
        ("success", SubagentStatus.completed),
        ("ok", SubagentStatus.completed),
        ("error", SubagentStatus.failed),
        ("xyz", SubagentStatus.inProgress)
    ])
    func statusFromString(rawAndExpected: (String, SubagentStatus)) {
        let (raw, expected) = rawAndExpected
        #expect(SubagentStatus.from(rawString: raw) == expected)
    }

    @Test("SubagentStatus tam eslesme korunmali", arguments: [
        ("spawned", SubagentStatus.spawned),
        ("in_progress", SubagentStatus.inProgress),
        ("completed", SubagentStatus.completed),
        ("failed", SubagentStatus.failed)
    ])
    func statusExactMatch(rawAndExpected: (String, SubagentStatus)) {
        let (raw, expected) = rawAndExpected
        #expect(SubagentStatus.from(rawString: raw) == expected)
    }
}
