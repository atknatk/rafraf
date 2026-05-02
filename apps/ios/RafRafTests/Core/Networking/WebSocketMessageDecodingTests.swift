import Foundation
import Testing
@testable import RafRaf

/// Claude Agent Teams WebSocket mesaj decoding testleri (T1.6).
/// Backend `apps/backend/app/schemas/messages.py` icindeki Pydantic
/// payload modellerine bire bir uygundur. Snake_case (backend) →
/// camelCase (Swift) donusumu test edilir.
@Suite("Agent Teams WebSocketMessage Decoding Tests")
struct WebSocketMessageDecodingTests {

    // MARK: - Helpers

    /// Router'in kullandigi decoder ile ayni: explicit snake_case CodingKeys
    /// kontrat kaynagidir; `.convertFromSnakeCase` strategy uygulanmaz (T1.6-fix C1).
    private static func makeDecoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .custom { decoder in
            let container = try decoder.singleValueContainer()
            let raw = try container.decode(String.self)
            if let date = WebSocketISODateParser.parse(raw) {
                return date
            }
            throw DecodingError.dataCorruptedError(
                in: container,
                debugDescription: "ISO8601 tarih ayristirilamadi: \(raw)"
            )
        }
        return decoder
    }

    private static func makeEncoder() -> JSONEncoder {
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        return encoder
    }

    // MARK: - SessionInit

    @Test("session.init mesaji decode edilmeli")
    func sessionInitDecode() throws {
        let json = #"""
        {
            "id": "msg-1",
            "type": "session.init",
            "content": {
                "session_id": "sess-abc",
                "model": "claude-opus-4-7",
                "permission_mode": "default",
                "api_key_source": "subscription",
                "cwd": "/Users/me/project",
                "agent_teams_enabled": true,
                "initialized_at": "2026-04-02T12:34:56Z"
            }
        }
        """#
        let data = try #require(json.data(using: .utf8))
        let message = try Self.makeDecoder().decode(WebSocketBaseMessage.self, from: data)

        #expect(message.type == "session.init")
        guard case .sessionInit(let payload) = message.content else {
            Issue.record("Content sessionInit olmali")
            return
        }
        #expect(payload.sessionId == "sess-abc")
        #expect(payload.model == "claude-opus-4-7")
        #expect(payload.permissionMode == "default")
        #expect(payload.apiKeySource == "subscription")
        #expect(payload.cwd == "/Users/me/project")
        #expect(payload.agentTeamsEnabled == true)
    }

    @Test("SessionInitContent round-trip encode/decode")
    func sessionInitRoundTrip() throws {
        let original = SessionInitContent(
            sessionId: "sess-x",
            model: "claude-opus-4-7",
            permissionMode: "auto",
            apiKeySource: "subscription",
            cwd: "/tmp",
            agentTeamsEnabled: true,
            initializedAt: Date(timeIntervalSince1970: 1_700_000_000)
        )
        let data = try Self.makeEncoder().encode(original)
        let decoded = try Self.makeDecoder().decode(SessionInitContent.self, from: data)
        #expect(decoded == original)
    }

    // MARK: - SubagentSpawned

    @Test("subagent.spawned mesaji decode edilmeli")
    func subagentSpawnedDecode() throws {
        let json = #"""
        {
            "id": "msg-2",
            "type": "subagent.spawned",
            "content": {
                "task_id": "task-1",
                "name": "code-reviewer",
                "description": "Reviews changed files",
                "prompt_preview": "Review the diff in src/...",
                "subagent_type": "general",
                "isolation": "worktree",
                "started_at": "2026-04-02T12:34:56.789012"
            }
        }
        """#
        let data = try #require(json.data(using: .utf8))
        let message = try Self.makeDecoder().decode(WebSocketBaseMessage.self, from: data)

        guard case .subagentSpawned(let payload) = message.content else {
            Issue.record("Content subagentSpawned olmali")
            return
        }
        #expect(payload.taskId == "task-1")
        #expect(payload.name == "code-reviewer")
        #expect(payload.description == "Reviews changed files")
        #expect(payload.promptPreview == "Review the diff in src/...")
        #expect(payload.subagentType == "general")
        #expect(payload.isolation == "worktree")
    }

    @Test("subagent.spawned opsiyonel alanlar olmadan decode edilmeli")
    func subagentSpawnedMinimalDecode() throws {
        let json = #"""
        {
            "id": "msg-2b",
            "type": "subagent.spawned",
            "content": {
                "task_id": "task-1b",
                "name": "writer",
                "prompt_preview": "Write docs",
                "started_at": "2026-04-02T12:34:56Z"
            }
        }
        """#
        let data = try #require(json.data(using: .utf8))
        let message = try Self.makeDecoder().decode(WebSocketBaseMessage.self, from: data)

        guard case .subagentSpawned(let payload) = message.content else {
            Issue.record("Content subagentSpawned olmali")
            return
        }
        #expect(payload.taskId == "task-1b")
        #expect(payload.description == nil)
        #expect(payload.subagentType == nil)
        #expect(payload.isolation == nil)
    }

    // MARK: - SubagentProgress

    @Test("subagent.progress mesaji decode edilmeli")
    func subagentProgressDecode() throws {
        let json = #"""
        {
            "id": "msg-3",
            "type": "subagent.progress",
            "content": {
                "task_id": "task-1",
                "status": "in_progress",
                "activity": "Editing config.toml",
                "updated_at": "2026-04-02T12:35:00Z"
            }
        }
        """#
        let data = try #require(json.data(using: .utf8))
        let message = try Self.makeDecoder().decode(WebSocketBaseMessage.self, from: data)

        guard case .subagentProgress(let payload) = message.content else {
            Issue.record("Content subagentProgress olmali")
            return
        }
        #expect(payload.taskId == "task-1")
        #expect(payload.status == "in_progress")
        #expect(payload.activity == "Editing config.toml")
    }

    @Test("SubagentProgressContent round-trip encode/decode")
    func subagentProgressRoundTrip() throws {
        let original = SubagentProgressContent(
            taskId: "task-9",
            status: "queued",
            activity: "Waiting",
            updatedAt: Date(timeIntervalSince1970: 1_700_000_100)
        )
        let data = try Self.makeEncoder().encode(original)
        let decoded = try Self.makeDecoder().decode(SubagentProgressContent.self, from: data)
        #expect(decoded == original)
    }

    // MARK: - SubagentCompleted

    @Test("subagent.completed mesaji decode edilmeli")
    func subagentCompletedDecode() throws {
        let json = #"""
        {
            "id": "msg-4",
            "type": "subagent.completed",
            "content": {
                "task_id": "task-1",
                "status": "completed",
                "summary": "Refactored auth flow",
                "total_tokens": 4321,
                "tool_uses": 12,
                "duration_ms": 5500,
                "completed_at": "2026-04-02T12:36:00Z"
            }
        }
        """#
        let data = try #require(json.data(using: .utf8))
        let message = try Self.makeDecoder().decode(WebSocketBaseMessage.self, from: data)

        guard case .subagentCompleted(let payload) = message.content else {
            Issue.record("Content subagentCompleted olmali")
            return
        }
        #expect(payload.taskId == "task-1")
        #expect(payload.status == "completed")
        #expect(payload.summary == "Refactored auth flow")
        #expect(payload.totalTokens == 4321)
        #expect(payload.toolUses == 12)
        #expect(payload.durationMs == 5500)
    }

    @Test("subagent.completed failed status decode edilmeli (summary nil)")
    func subagentCompletedFailedDecode() throws {
        let json = #"""
        {
            "id": "msg-4b",
            "type": "subagent.completed",
            "content": {
                "task_id": "task-2",
                "status": "failed",
                "total_tokens": 100,
                "tool_uses": 1,
                "duration_ms": 200,
                "completed_at": "2026-04-02T12:36:00Z"
            }
        }
        """#
        let data = try #require(json.data(using: .utf8))
        let message = try Self.makeDecoder().decode(WebSocketBaseMessage.self, from: data)

        guard case .subagentCompleted(let payload) = message.content else {
            Issue.record("Content subagentCompleted olmali")
            return
        }
        #expect(payload.status == "failed")
        #expect(payload.summary == nil)
    }

    // MARK: - RateLimitInfo

    @Test("rate_limit.info mesaji decode edilmeli")
    func rateLimitInfoDecode() throws {
        let json = #"""
        {
            "id": "msg-5",
            "type": "rate_limit.info",
            "content": {
                "status": "limited",
                "rate_limit_type": "five_hour",
                "resets_at": 1735000000,
                "overage_status": "in_overage",
                "is_using_overage": true
            }
        }
        """#
        let data = try #require(json.data(using: .utf8))
        let message = try Self.makeDecoder().decode(WebSocketBaseMessage.self, from: data)

        guard case .rateLimitInfo(let payload) = message.content else {
            Issue.record("Content rateLimitInfo olmali")
            return
        }
        #expect(payload.status == "limited")
        #expect(payload.rateLimitType == "five_hour")
        #expect(payload.resetsAt == 1_735_000_000)
        #expect(payload.overageStatus == "in_overage")
        #expect(payload.isUsingOverage == true)
    }

    @Test("RateLimitInfoContent round-trip encode/decode")
    func rateLimitInfoRoundTrip() throws {
        let original = RateLimitInfoContent(
            status: "allowed",
            rateLimitType: "five_hour",
            resetsAt: 1_700_000_000,
            overageStatus: "none",
            isUsingOverage: false
        )
        let data = try Self.makeEncoder().encode(original)
        let decoded = try Self.makeDecoder().decode(RateLimitInfoContent.self, from: data)
        #expect(decoded == original)
    }

    // MARK: - SessionTitle

    @Test("session.title mesaji decode edilmeli")
    func sessionTitleDecode() throws {
        let json = #"""
        {
            "id": "msg-6",
            "type": "session.title",
            "content": {
                "session_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
                "ai_title": "Refactor auth flow to JWT",
                "generated_at": "2026-04-02T12:37:00Z"
            }
        }
        """#
        let data = try #require(json.data(using: .utf8))
        let message = try Self.makeDecoder().decode(WebSocketBaseMessage.self, from: data)

        guard case .sessionTitle(let payload) = message.content else {
            Issue.record("Content sessionTitle olmali")
            return
        }
        #expect(payload.sessionId == UUID(uuidString: "f47ac10b-58cc-4372-a567-0e02b2c3d479"))
        #expect(payload.aiTitle == "Refactor auth flow to JWT")
    }

    // MARK: - SessionPrOpened

    @Test("session.pr_opened mesaji decode edilmeli")
    func sessionPrOpenedDecode() throws {
        let json = #"""
        {
            "id": "msg-7",
            "type": "session.pr_opened",
            "content": {
                "session_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
                "pr_number": 42,
                "pr_url": "https://github.com/org/repo/pull/42",
                "pr_repository": "org/repo",
                "opened_at": "2026-04-02T12:38:00Z"
            }
        }
        """#
        let data = try #require(json.data(using: .utf8))
        let message = try Self.makeDecoder().decode(WebSocketBaseMessage.self, from: data)

        guard case .sessionPrOpened(let payload) = message.content else {
            Issue.record("Content sessionPrOpened olmali")
            return
        }
        #expect(payload.sessionId == UUID(uuidString: "f47ac10b-58cc-4372-a567-0e02b2c3d479"))
        #expect(payload.prNumber == 42)
        #expect(payload.prUrl == "https://github.com/org/repo/pull/42")
        #expect(payload.prRepository == "org/repo")
    }

    @Test("SessionPrOpenedContent round-trip encode/decode")
    func sessionPrOpenedRoundTrip() throws {
        let sessionUuid = try #require(UUID(uuidString: "f47ac10b-58cc-4372-a567-0e02b2c3d479"))
        let original = SessionPrOpenedContent(
            sessionId: sessionUuid,
            prNumber: 7,
            prUrl: "https://github.com/x/y/pull/7",
            prRepository: "x/y",
            openedAt: Date(timeIntervalSince1970: 1_700_000_200)
        )
        let data = try Self.makeEncoder().encode(original)
        let decoded = try Self.makeDecoder().decode(SessionPrOpenedContent.self, from: data)
        #expect(decoded == original)
    }

    // MARK: - UsageReport

    @Test("usage.report mesaji decode edilmeli")
    func usageReportDecode() throws {
        let json = #"""
        {
            "id": "msg-8",
            "type": "usage.report",
            "content": {
                "five_hour_pct": 75,
                "seven_day_pct": 42,
                "five_hour_resets_at": 1735018000,
                "seven_day_resets_at": 1735604800,
                "reported_at": 1735000000
            }
        }
        """#
        let data = try #require(json.data(using: .utf8))
        let message = try Self.makeDecoder().decode(WebSocketBaseMessage.self, from: data)

        guard case .usageReport(let payload) = message.content else {
            Issue.record("Content usageReport olmali")
            return
        }
        #expect(payload.fiveHourPct == 75)
        #expect(payload.sevenDayPct == 42)
        #expect(payload.fiveHourResetsAt == 1_735_018_000)
        #expect(payload.sevenDayResetsAt == 1_735_604_800)
        #expect(payload.reportedAt == 1_735_000_000)
    }

    @Test("UsageReportContent overage durumunda 100'u asabilir")
    func usageReportOverageDecode() throws {
        let json = #"""
        {
            "five_hour_pct": 125,
            "seven_day_pct": 89,
            "five_hour_resets_at": 1735018000,
            "seven_day_resets_at": 1735604800,
            "reported_at": 1735000000
        }
        """#
        let data = try #require(json.data(using: .utf8))
        let payload = try Self.makeDecoder().decode(UsageReportContent.self, from: data)
        #expect(payload.fiveHourPct == 125)
    }

    @Test("UsageReportContent round-trip encode/decode")
    func usageReportRoundTrip() throws {
        let original = UsageReportContent(
            fiveHourPct: 50,
            sevenDayPct: 25,
            fiveHourResetsAt: 1_700_000_000,
            sevenDayResetsAt: 1_700_086_400,
            reportedAt: 1_699_999_900
        )
        let data = try Self.makeEncoder().encode(original)
        let decoded = try Self.makeDecoder().decode(UsageReportContent.self, from: data)
        #expect(decoded == original)
    }

    // MARK: - Validation: Missing required fields

    @Test("Eksik task_id ile subagent.spawned decode hatasi vermeli")
    func subagentSpawnedMissingTaskIdFails() {
        let json = #"""
        {
            "name": "x",
            "prompt_preview": "...",
            "started_at": "2026-04-02T12:34:56Z"
        }
        """#
        guard let data = json.data(using: .utf8) else {
            Issue.record("UTF-8 encode basarisiz")
            return
        }
        #expect(throws: DecodingError.self) {
            try Self.makeDecoder().decode(SubagentSpawnedContent.self, from: data)
        }
    }

    @Test("Eksik five_hour_pct ile usage.report decode hatasi vermeli")
    func usageReportMissingFiveHourPctFails() {
        let json = #"""
        {
            "seven_day_pct": 50,
            "five_hour_resets_at": 1,
            "seven_day_resets_at": 2,
            "reported_at": 3
        }
        """#
        guard let data = json.data(using: .utf8) else {
            Issue.record("UTF-8 encode basarisiz")
            return
        }
        #expect(throws: DecodingError.self) {
            try Self.makeDecoder().decode(UsageReportContent.self, from: data)
        }
    }

    @Test("Bozuk ISO8601 datetime ile subagent.spawned decode hatasi vermeli")
    func subagentSpawnedMalformedDateFails() {
        let json = #"""
        {
            "task_id": "t",
            "name": "n",
            "prompt_preview": "p",
            "started_at": "not-a-date"
        }
        """#
        guard let data = json.data(using: .utf8) else {
            Issue.record("UTF-8 encode basarisiz")
            return
        }
        #expect(throws: DecodingError.self) {
            try Self.makeDecoder().decode(SubagentSpawnedContent.self, from: data)
        }
    }

    // MARK: - MessageType raw values

    @Test("Yeni Agent Teams message type rawValue'lari dogru olmali")
    func agentTeamsMessageTypeRawValues() {
        #expect(WebSocketMessageType.sessionInit.rawValue == "session.init")
        #expect(WebSocketMessageType.subagentSpawned.rawValue == "subagent.spawned")
        #expect(WebSocketMessageType.subagentProgress.rawValue == "subagent.progress")
        #expect(WebSocketMessageType.subagentCompleted.rawValue == "subagent.completed")
        #expect(WebSocketMessageType.rateLimitInfo.rawValue == "rate_limit.info")
        #expect(WebSocketMessageType.sessionTitle.rawValue == "session.title")
        #expect(WebSocketMessageType.sessionPrOpened.rawValue == "session.pr_opened")
        #expect(WebSocketMessageType.usageReport.rawValue == "usage.report")
    }

    // MARK: - Router end-to-end

    @Test("Router uzerinden session.init mesaji decode + log edilmeli")
    func routerHandlesAgentTeamsMessage() async throws {
        let router = WebSocketMessageRouter()
        let json = #"""
        {
            "id": "msg-r1",
            "type": "session.init",
            "content": {
                "session_id": "sess-r",
                "model": "claude-opus-4-7",
                "permission_mode": "default",
                "api_key_source": "subscription",
                "cwd": "/tmp",
                "agent_teams_enabled": true,
                "initialized_at": "2026-04-02T12:34:56Z"
            }
        }
        """#
        let message = try await router.route(json)
        #expect(message.type == "session.init")
        guard case .sessionInit(let payload) = message.content else {
            Issue.record("Content sessionInit olmali")
            return
        }
        #expect(payload.sessionId == "sess-r")
    }

    @Test("Router uzerinden usage.report mesaji decode edilmeli")
    func routerHandlesUsageReport() async throws {
        let router = WebSocketMessageRouter()
        let json = #"""
        {
            "id": "msg-r2",
            "type": "usage.report",
            "content": {
                "five_hour_pct": 33,
                "seven_day_pct": 11,
                "five_hour_resets_at": 1735018000,
                "seven_day_resets_at": 1735604800,
                "reported_at": 1735000000
            }
        }
        """#
        let message = try await router.route(json)
        guard case .usageReport(let payload) = message.content else {
            Issue.record("Content usageReport olmali")
            return
        }
        #expect(payload.fiveHourPct == 33)
        #expect(payload.sevenDayPct == 11)
    }

    // MARK: - WebSocketISODateParser

    @Test("WebSocketISODateParser ISO8601 with Z parse etmeli")
    func isoParserBasic() {
        let date = WebSocketISODateParser.parse("2026-04-02T12:34:56Z")
        #expect(date != nil)
    }

    @Test("WebSocketISODateParser fractional seconds parse etmeli")
    func isoParserFractional() {
        let date = WebSocketISODateParser.parse("2026-04-02T12:34:56.789Z")
        #expect(date != nil)
    }

    @Test("WebSocketISODateParser Pydantic naive (offset'siz) parse etmeli")
    func isoParserPydanticNaive() {
        let date = WebSocketISODateParser.parse("2026-04-02T12:34:56.789012")
        #expect(date != nil)
    }

    @Test("WebSocketISODateParser bozuk girdi nil donmeli")
    func isoParserMalformed() {
        let date = WebSocketISODateParser.parse("not-a-date")
        #expect(date == nil)
    }
}
