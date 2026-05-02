import Foundation
import Testing
@testable import RafRaf

/// SubagentDetailSheet pure-helper testleri (T3.1).
///
/// Sheet'in tum sectionlari gercek bir subagent verisi icin render edilebilir
/// olmali. Burada test edilen pure fonksiyonlar (truncatePromptForDisplay /
/// shouldShowExpandToggle) UI render mantigini deterministik kilan helper'lar.
@Suite("SubagentDetailSheet Tests")
struct SubagentDetailSheetTests {

    // MARK: - Helpers

    private func makeSubagent(
        id: String = "task-detail-1",
        promptPreview: String = "do something",
        status: SubagentStatus = .completed,
        summary: String? = "All sections rendered",
        totalTokens: Int? = 12_800,
        toolUses: Int? = 7,
        durationMs: Int? = 32_500,
        isolation: String? = "worktree",
        subagentType: String? = "developer",
        spawnedAt: Date = Date(timeIntervalSince1970: 100),
        updatedAt: Date? = Date(timeIntervalSince1970: 150),
        completedAt: Date? = Date(timeIntervalSince1970: 200)
    ) -> Subagent {
        Subagent(
            id: id,
            sessionId: "sess-1",
            parentTaskId: nil,
            name: "developer",
            description: "Implement feature X",
            promptPreview: promptPreview,
            subagentType: subagentType,
            isolation: isolation,
            status: status,
            summary: summary,
            totalTokens: totalTokens,
            toolUses: toolUses,
            durationMs: durationMs,
            activity: nil,
            spawnedAt: spawnedAt,
            updatedAt: updatedAt,
            completedAt: completedAt
        )
    }

    // MARK: - truncatePromptForDisplay

    @Test("Prompt 280 karakterden kisaysa truncate yapmaz")
    func truncate_short() {
        let prompt = String(repeating: "a", count: 100)
        let result = SubagentDetailSheet.truncatePromptForDisplay(prompt, expanded: false)
        #expect(result == prompt)
        #expect(result.hasSuffix("…") == false)
    }

    @Test("Prompt 280'den uzun ve expanded false ise truncate eder")
    func truncate_long_collapsed() {
        let prompt = String(repeating: "a", count: 400)
        let result = SubagentDetailSheet.truncatePromptForDisplay(prompt, expanded: false)
        #expect(result.count == 281)
        #expect(result.hasSuffix("…"))
    }

    @Test("Prompt expanded true ise truncate yapmaz")
    func truncate_expanded() {
        let prompt = String(repeating: "a", count: 400)
        let result = SubagentDetailSheet.truncatePromptForDisplay(prompt, expanded: true)
        #expect(result == prompt)
        #expect(result.hasSuffix("…") == false)
    }

    // MARK: - shouldShowExpandToggle

    @Test("Show toggle 280 karakter ve uzeri icin true")
    func shouldShowToggle_threshold() {
        let short = String(repeating: "a", count: 280)
        let long = String(repeating: "a", count: 281)
        #expect(SubagentDetailSheet.shouldShowExpandToggle(for: short) == false)
        #expect(SubagentDetailSheet.shouldShowExpandToggle(for: long) == true)
    }

    // MARK: - Sheet construction (render-able for various states)

    @Test("Sheet completed subagent icin construct edilebilir")
    @MainActor
    func sheet_constructs_completed() {
        let sub = makeSubagent(status: .completed)
        let sheet = SubagentDetailSheet(subagent: sub)
        #expect(sheet.subagent.id == sub.id)
        #expect(sheet.subagent.status == .completed)
    }

    @Test("Sheet inProgress subagent icin construct edilebilir")
    @MainActor
    func sheet_constructs_inProgress() {
        let sub = makeSubagent(
            status: .inProgress,
            summary: nil,
            totalTokens: nil,
            toolUses: nil,
            durationMs: nil,
            completedAt: nil
        )
        let sheet = SubagentDetailSheet(subagent: sub)
        #expect(sheet.subagent.status == .inProgress)
        #expect(sheet.subagent.summary == nil)
        #expect(sheet.subagent.totalTokens == nil)
    }

    @Test("Sheet failed subagent icin construct edilebilir")
    @MainActor
    func sheet_constructs_failed() {
        let sub = makeSubagent(
            status: .failed,
            summary: "Found 1 issue: missing accessibility label"
        )
        let sheet = SubagentDetailSheet(subagent: sub)
        #expect(sheet.subagent.status == .failed)
        #expect(sheet.subagent.summary?.contains("missing accessibility") == true)
    }

    // MARK: - Field extraction

    @Test("Sheet isolation alani eksikse de calismali")
    @MainActor
    func sheet_constructs_no_isolation() {
        let sub = makeSubagent(isolation: nil)
        let sheet = SubagentDetailSheet(subagent: sub)
        #expect(sheet.subagent.isolation == nil)
    }

    @Test("Sheet timeline icin tum tarihler nil olabilir")
    @MainActor
    func sheet_constructs_no_timeline() {
        let sub = makeSubagent(updatedAt: nil, completedAt: nil)
        let sheet = SubagentDetailSheet(subagent: sub)
        #expect(sheet.subagent.updatedAt == nil)
        #expect(sheet.subagent.completedAt == nil)
        #expect(sheet.subagent.spawnedAt == Date(timeIntervalSince1970: 100))
    }
}
