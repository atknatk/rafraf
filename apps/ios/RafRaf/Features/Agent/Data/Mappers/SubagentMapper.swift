import Foundation

/// Bridge `subagent.*` WebSocket Content struct'larini Domain
/// `Subagent` / `SubagentUpdate` modeline cevirir.
///
/// T1.6 commit fb3b183 ile iOS tarafinda tanimlanan
/// `SubagentSpawnedContent`, `SubagentProgressContent`,
/// `SubagentCompletedContent` payload'lari T1.7'de bu mapper araciligi ile
/// Domain katmanina aktarilir.
enum SubagentMapper {

    /// `subagent.spawned` -> Domain `SubagentUpdate.spawn`.
    /// `parentTaskId` su an payload'da yok — ileride bridge eklediginde
    /// burada eslenecek.
    static func toUpdate(
        spawned content: SubagentSpawnedContent,
        sessionId: String,
        parentTaskId: String? = nil
    ) -> SubagentUpdate {
        let subagent = Subagent(
            id: content.taskId,
            sessionId: sessionId,
            parentTaskId: parentTaskId,
            name: content.name,
            description: content.description,
            promptPreview: content.promptPreview,
            subagentType: content.subagentType,
            isolation: content.isolation,
            status: .spawned,
            summary: nil,
            totalTokens: nil,
            toolUses: nil,
            durationMs: nil,
            activity: nil,
            spawnedAt: content.startedAt,
            updatedAt: nil,
            completedAt: nil
        )
        return .spawn(subagent)
    }

    /// `subagent.progress` -> Domain `SubagentUpdate.progress`.
    static func toUpdate(
        progress content: SubagentProgressContent,
        sessionId: String
    ) -> SubagentUpdate {
        .progress(
            taskId: content.taskId,
            sessionId: sessionId,
            status: SubagentStatus.from(rawString: content.status),
            activity: content.activity,
            updatedAt: content.updatedAt
        )
    }

    /// `subagent.completed` -> Domain `SubagentUpdate.completed`.
    static func toUpdate(
        completed content: SubagentCompletedContent,
        sessionId: String
    ) -> SubagentUpdate {
        .completed(
            taskId: content.taskId,
            sessionId: sessionId,
            status: SubagentStatus.from(rawString: content.status),
            summary: content.summary,
            totalTokens: content.totalTokens,
            toolUses: content.toolUses,
            durationMs: content.durationMs,
            completedAt: content.completedAt
        )
    }
}
