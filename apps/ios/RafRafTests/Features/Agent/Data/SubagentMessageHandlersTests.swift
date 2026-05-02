import Foundation
import Testing
@testable import RafRaf

/// Subagent WebSocket handler testleri (T1.7).
/// Handler'lar Bridge'den gelen WebSocketBaseMessage'i SubagentRepository'ye
/// dogru sekilde tasiyor mu?
@Suite("Subagent Message Handlers Tests")
struct SubagentMessageHandlersTests {

    private static let now = Date(timeIntervalSince1970: 1_700_000_000)

    private func makeMessage(
        type: WebSocketMessageType,
        sessionId: String?,
        content: WebSocketContent?
    ) -> WebSocketBaseMessage {
        WebSocketBaseMessage(
            id: "msg-1",
            type: type.rawValue,
            content: content,
            metadata: WebSocketMessageMetadata(sessionId: sessionId),
            attachments: nil
        )
    }

    @Test("SubagentSpawnedHandler subagent kaydini repository'ye eklemeli")
    func spawnedHandlerAddsSubagent() async {
        let repo = SubagentRepositoryImpl()
        let handler = SubagentSpawnedHandler(repository: repo)
        let content = SubagentSpawnedContent(
            taskId: "task-1",
            name: "developer",
            description: "x",
            promptPreview: "hello",
            subagentType: "general-purpose",
            isolation: "worktree",
            startedAt: Self.now
        )
        let message = makeMessage(
            type: .subagentSpawned,
            sessionId: "sess-1",
            content: .subagentSpawned(content)
        )

        await handler.handle(message)

        let snapshot = await repo.currentSubagents(sessionId: "sess-1")
        #expect(snapshot.count == 1)
        #expect(snapshot[0].id == "task-1")
        #expect(snapshot[0].isolation == "worktree")
    }

    @Test("SubagentSpawnedHandler sessionId yoksa sessizce yoksaymali")
    func spawnedHandlerSkipsWhenNoSession() async {
        let repo = SubagentRepositoryImpl()
        let handler = SubagentSpawnedHandler(repository: repo)
        let content = SubagentSpawnedContent(
            taskId: "task-1",
            name: "x",
            description: nil,
            promptPreview: "p",
            subagentType: nil,
            isolation: nil,
            startedAt: Self.now
        )
        let message = makeMessage(
            type: .subagentSpawned,
            sessionId: nil,
            content: .subagentSpawned(content)
        )
        await handler.handle(message)

        let all = await repo.currentAllSubagents()
        #expect(all.isEmpty)
    }

    @Test("SubagentProgressHandler mevcut subagent'i gunceller")
    func progressHandlerUpdates() async {
        let repo = SubagentRepositoryImpl()
        // Once spawn
        await repo.apply(update: .spawn(Subagent(
            id: "task-1",
            sessionId: "sess-1",
            parentTaskId: nil,
            name: "n",
            description: nil,
            promptPreview: "p",
            subagentType: nil,
            isolation: nil,
            status: .spawned,
            summary: nil,
            totalTokens: nil,
            toolUses: nil,
            durationMs: nil,
            activity: nil,
            spawnedAt: Self.now,
            updatedAt: nil,
            completedAt: nil
        )))

        let handler = SubagentProgressHandler(repository: repo)
        let content = SubagentProgressContent(
            taskId: "task-1",
            status: "in_progress",
            activity: "compiling",
            updatedAt: Self.now.addingTimeInterval(50)
        )
        let message = makeMessage(
            type: .subagentProgress,
            sessionId: "sess-1",
            content: .subagentProgress(content)
        )
        await handler.handle(message)

        let snapshot = await repo.currentSubagents(sessionId: "sess-1")
        #expect(snapshot[0].status == .inProgress)
        #expect(snapshot[0].activity == "compiling")
    }

    @Test("SubagentCompletedHandler mevcut subagent'i finalize eder")
    func completedHandlerFinalizes() async {
        let repo = SubagentRepositoryImpl()
        await repo.apply(update: .spawn(Subagent(
            id: "task-1",
            sessionId: "sess-1",
            parentTaskId: nil,
            name: "n",
            description: nil,
            promptPreview: "p",
            subagentType: nil,
            isolation: nil,
            status: .spawned,
            summary: nil,
            totalTokens: nil,
            toolUses: nil,
            durationMs: nil,
            activity: nil,
            spawnedAt: Self.now,
            updatedAt: nil,
            completedAt: nil
        )))

        let handler = SubagentCompletedHandler(repository: repo)
        let content = SubagentCompletedContent(
            taskId: "task-1",
            status: "completed",
            summary: "ok",
            totalTokens: 200,
            toolUses: 3,
            durationMs: 1500,
            completedAt: Self.now.addingTimeInterval(100)
        )
        let message = makeMessage(
            type: .subagentCompleted,
            sessionId: "sess-1",
            content: .subagentCompleted(content)
        )
        await handler.handle(message)

        let snapshot = await repo.currentSubagents(sessionId: "sess-1")
        #expect(snapshot[0].status == .completed)
        #expect(snapshot[0].summary == "ok")
        #expect(snapshot[0].totalTokens == 200)
    }
}
