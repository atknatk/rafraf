import Foundation
import os

/// Bridge contract drift gozlemlenebilirligi icin paylasilan logger
/// (`WebSocketBaseMessage.init(from:)` payload decode fallback'lari).
private let webSocketMessageLogger = Logger(
    subsystem: "com.rafraf",
    category: "WebSocketMessage"
)

// MARK: - WebSocket Message Types

/// WebSocket mesaj tipleri.
/// `shared/api-contracts/ws/websocket-messages.json` kontratina uygun.
enum WebSocketMessageType: String, Codable, Sendable {
    case connectionAck = "connection_ack"
    case text
    case error
    case progress
    case ping
    case pong
    // Streaming response types
    case chatStream = "chat.stream"
    case chatStreamEnd = "chat.stream_end"
    // Code diff type
    case codeDiff = "code.diff"
    // Proactive suggestion type
    case suggestion = "suggestion"
    // GitHub webhook events (server → client broadcast)
    case githubEvent = "github_event"
    // Agent proactive status change broadcasts
    case agentStatusChange = "agent_status_change"
    // Typing indicators (server → client)
    case typingStart = "typing.start"
    case typingEnd = "typing.end"
    // Stream control (client → server)
    case cancelStream = "stream.cancel"
    // Stream cancelled ack (server → client)
    case streamCancelled = "stream.cancelled"
    // Task status updates (server → client)
    case taskStatus = "task_status"
    // Claude Agent Teams events (server → client, sourced from bridge stream-json)
    case sessionInit = "session.init"
    case subagentSpawned = "subagent.spawned"
    case subagentProgress = "subagent.progress"
    case subagentCompleted = "subagent.completed"
    case rateLimitInfo = "rate_limit.info"
    case sessionTitle = "session.title"
    case sessionPrOpened = "session.pr_opened"
    case usageReport = "usage.report"
}

/// Mesaj yonu.
enum WebSocketMessageDirection: String, Codable, Sendable {
    case clientToServer = "client_to_server"
    case serverToClient = "server_to_client"
}

// MARK: - Base Message

/// Temel WebSocket mesaj yapisi.
/// Tum mesajlar bu yapiya uygun encode/decode edilir.
/// `id` alani opsiyoneldir — backend bazi broadcast mesajlarinda gondermeyebilir.
struct WebSocketBaseMessage: Codable, Sendable {
    let id: String
    let type: String
    let content: WebSocketContent?
    let metadata: WebSocketMessageMetadata?
    let attachments: [WebSocketMessageAttachment]?

    enum CodingKeys: String, CodingKey {
        case id, type, content, metadata, attachments
    }

    enum ExtraKeys: String, CodingKey {
        case event, action, repo, summary, hostId, status, reason, isNew
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.id = (try? container.decodeIfPresent(String.self, forKey: .id)) ?? UUID().uuidString
        self.type = try container.decode(String.self, forKey: .type)
        self.metadata = try? container.decodeIfPresent(WebSocketMessageMetadata.self, forKey: .metadata)
        self.attachments = try? container.decodeIfPresent([WebSocketMessageAttachment].self, forKey: .attachments)

        // GitHub event messages store payload at top level instead of `content`
        if self.type == WebSocketMessageType.githubEvent.rawValue {
            let extra = try decoder.container(keyedBy: ExtraKeys.self)
            let event = (try? extra.decodeIfPresent(String.self, forKey: .event)) ?? ""
            let action = (try? extra.decodeIfPresent(String.self, forKey: .action)) ?? ""
            let repo = (try? extra.decodeIfPresent(String.self, forKey: .repo)) ?? ""
            let summary = (try? extra.decodeIfPresent(GitHubEventSummaryPayload.self, forKey: .summary)) ?? GitHubEventSummaryPayload()
            self.content = .githubEvent(GitHubEventPayload(event: event, action: action, repo: repo, summary: summary))
        } else if self.type == WebSocketMessageType.agentStatusChange.rawValue {
            let extra = try decoder.container(keyedBy: ExtraKeys.self)
            let hostId = (try? extra.decodeIfPresent(String.self, forKey: .hostId)) ?? ""
            let status = (try? extra.decodeIfPresent(String.self, forKey: .status)) ?? ""
            let reason = try? extra.decodeIfPresent(String.self, forKey: .reason)
            let isNew = try? extra.decodeIfPresent(Bool.self, forKey: .isNew)
            self.content = .agentStatusChange(AgentStatusChangePayload(hostId: hostId, status: status, reason: reason, isNew: isNew))
        } else if self.type == WebSocketMessageType.taskStatus.rawValue {
            // task_status mesajini dogrudan decode et (singleValueContainer ambiguity onleme)
            if let taskContent = try? container.decodeIfPresent(TaskStatusContent.self, forKey: .content) {
                self.content = .taskStatus(taskContent)
            } else {
                self.content = nil
            }
        } else if self.type == WebSocketMessageType.sessionInit.rawValue {
            // M2: silent try? yerine yapilandirilmis log — bridge contract drift gorulebilsin.
            do {
                let payload = try container.decodeIfPresent(SessionInitContent.self, forKey: .content)
                self.content = payload.map { .sessionInit($0) }
            } catch {
                webSocketMessageLogger.warning("session.init payload decode failed: \(String(describing: error))")
                self.content = nil
            }
        } else if self.type == WebSocketMessageType.subagentSpawned.rawValue {
            do {
                let payload = try container.decodeIfPresent(SubagentSpawnedContent.self, forKey: .content)
                self.content = payload.map { .subagentSpawned($0) }
            } catch {
                webSocketMessageLogger.warning("subagent.spawned payload decode failed: \(String(describing: error))")
                self.content = nil
            }
        } else if self.type == WebSocketMessageType.subagentProgress.rawValue {
            do {
                let payload = try container.decodeIfPresent(SubagentProgressContent.self, forKey: .content)
                self.content = payload.map { .subagentProgress($0) }
            } catch {
                webSocketMessageLogger.warning("subagent.progress payload decode failed: \(String(describing: error))")
                self.content = nil
            }
        } else if self.type == WebSocketMessageType.subagentCompleted.rawValue {
            do {
                let payload = try container.decodeIfPresent(SubagentCompletedContent.self, forKey: .content)
                self.content = payload.map { .subagentCompleted($0) }
            } catch {
                webSocketMessageLogger.warning("subagent.completed payload decode failed: \(String(describing: error))")
                self.content = nil
            }
        } else if self.type == WebSocketMessageType.rateLimitInfo.rawValue {
            do {
                let payload = try container.decodeIfPresent(RateLimitInfoContent.self, forKey: .content)
                self.content = payload.map { .rateLimitInfo($0) }
            } catch {
                webSocketMessageLogger.warning("rate_limit.info payload decode failed: \(String(describing: error))")
                self.content = nil
            }
        } else if self.type == WebSocketMessageType.sessionTitle.rawValue {
            do {
                let payload = try container.decodeIfPresent(SessionTitleContent.self, forKey: .content)
                self.content = payload.map { .sessionTitle($0) }
            } catch {
                webSocketMessageLogger.warning("session.title payload decode failed: \(String(describing: error))")
                self.content = nil
            }
        } else if self.type == WebSocketMessageType.sessionPrOpened.rawValue {
            do {
                let payload = try container.decodeIfPresent(SessionPrOpenedContent.self, forKey: .content)
                self.content = payload.map { .sessionPrOpened($0) }
            } catch {
                webSocketMessageLogger.warning("session.pr_opened payload decode failed: \(String(describing: error))")
                self.content = nil
            }
        } else if self.type == WebSocketMessageType.usageReport.rawValue {
            do {
                let payload = try container.decodeIfPresent(UsageReportContent.self, forKey: .content)
                self.content = payload.map { .usageReport($0) }
            } catch {
                webSocketMessageLogger.warning("usage.report payload decode failed: \(String(describing: error))")
                self.content = nil
            }
        } else {
            self.content = try? container.decodeIfPresent(WebSocketContent.self, forKey: .content)
        }
    }

    init(
        id: String = UUID().uuidString,
        type: String,
        content: WebSocketContent? = nil,
        metadata: WebSocketMessageMetadata? = nil,
        attachments: [WebSocketMessageAttachment]? = nil
    ) {
        self.id = id
        self.type = type
        self.content = content
        self.metadata = metadata
        self.attachments = attachments
    }
}

// MARK: - Message Content

/// WebSocket mesaj icerigi.
/// Mesaj tipine gore string veya structured content olabilir.
enum WebSocketContent: Codable, Sendable {
    case text(String)
    case textResponse(TextResponseContent)
    case connectionAck(ConnectionAckContent)
    case error(ErrorMessageContent)
    case progress(ProgressMessageContent)
    case heartbeat(HeartbeatContent)
    case chatStream(ChatStreamContent)
    case chatStreamEnd(ChatStreamEndContent)
    case codeDiff(CodeDiffContent)
    case suggestion(SuggestionContent)
    case githubEvent(GitHubEventPayload)
    case agentStatusChange(AgentStatusChangePayload)
    case taskStatus(TaskStatusContent)
    // Claude Agent Teams events (T1.6)
    case sessionInit(SessionInitContent)
    case subagentSpawned(SubagentSpawnedContent)
    case subagentProgress(SubagentProgressContent)
    case subagentCompleted(SubagentCompletedContent)
    case rateLimitInfo(RateLimitInfoContent)
    case sessionTitle(SessionTitleContent)
    case sessionPrOpened(SessionPrOpenedContent)
    case usageReport(UsageReportContent)

    // MARK: M1 (deferred — Faz 1 polish queue)
    // Asagidaki singleValueContainer fall-through 8 yeni Agent Teams Content
    // tipini denemiyor. Su an Agent Teams payload'lari WebSocketBaseMessage
    // init'inde type-dispatch ile decode edildiginden bu kullanilmiyor; ancak
    // birisi WebSocketContent.init(from:)'u dogrudan cagirirsa typeMismatch
    // olur. Cozum: enum'u type-discriminated polymorphic decode'a tasi.
    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()

        if let text = try? container.decode(String.self) {
            self = .text(text)
            return
        }

        // Streaming types (check before textResponse to avoid ambiguity)
        if let stream = try? container.decode(ChatStreamContent.self) {
            self = .chatStream(stream)
            return
        }

        if let streamEnd = try? container.decode(ChatStreamEndContent.self) {
            self = .chatStreamEnd(streamEnd)
            return
        }

        if let diff = try? container.decode(CodeDiffContent.self) {
            self = .codeDiff(diff)
            return
        }

        if let suggestion = try? container.decode(SuggestionContent.self) {
            self = .suggestion(suggestion)
            return
        }

        if let taskStatusContent = try? container.decode(TaskStatusContent.self) {
            self = .taskStatus(taskStatusContent)
            return
        }

        // Backend text response: {"text": "...", "model_used": "...", ...}
        if let textResponse = try? container.decode(TextResponseContent.self) {
            self = .textResponse(textResponse)
            return
        }

        if let ack = try? container.decode(ConnectionAckContent.self) {
            self = .connectionAck(ack)
            return
        }

        if let error = try? container.decode(ErrorMessageContent.self) {
            self = .error(error)
            return
        }

        if let progress = try? container.decode(ProgressMessageContent.self) {
            self = .progress(progress)
            return
        }

        if let heartbeat = try? container.decode(HeartbeatContent.self) {
            self = .heartbeat(heartbeat)
            return
        }

        throw DecodingError.dataCorruptedError(
            in: container,
            debugDescription: "WebSocket content tipi taninamadi"
        )
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .text(let value):
            try container.encode(value)
        case .textResponse(let value):
            try container.encode(value)
        case .connectionAck(let value):
            try container.encode(value)
        case .error(let value):
            try container.encode(value)
        case .progress(let value):
            try container.encode(value)
        case .heartbeat(let value):
            try container.encode(value)
        case .chatStream(let value):
            try container.encode(value)
        case .chatStreamEnd(let value):
            try container.encode(value)
        case .codeDiff(let value):
            try container.encode(value)
        case .suggestion(let value):
            try container.encode(value)
        case .githubEvent(let value):
            try container.encode(value)
        case .agentStatusChange(let value):
            try container.encode(value)
        case .taskStatus(let value):
            try container.encode(value)
        case .sessionInit(let value):
            try container.encode(value)
        case .subagentSpawned(let value):
            try container.encode(value)
        case .subagentProgress(let value):
            try container.encode(value)
        case .subagentCompleted(let value):
            try container.encode(value)
        case .rateLimitInfo(let value):
            try container.encode(value)
        case .sessionTitle(let value):
            try container.encode(value)
        case .sessionPrOpened(let value):
            try container.encode(value)
        case .usageReport(let value):
            try container.encode(value)
        }
    }
}

// MARK: - Metadata

/// Mesaj metadata bilgileri.
struct WebSocketMessageMetadata: Codable, Sendable {
    let timestamp: String
    let sessionId: String?
    let projectId: String?
    let agentId: String?
    let messageId: String?
    let direction: String

    enum CodingKeys: String, CodingKey {
        case timestamp
        case sessionId = "session_id"
        case projectId = "project_id"
        case agentId = "agent_id"
        case messageId = "message_id"
        case direction
    }

    init(
        timestamp: String = ISO8601DateFormatter().string(from: Date()),
        sessionId: String? = nil,
        projectId: String? = nil,
        agentId: String? = nil,
        messageId: String? = nil,
        direction: String = WebSocketMessageDirection.clientToServer.rawValue
    ) {
        self.timestamp = timestamp
        self.sessionId = sessionId
        self.projectId = projectId
        self.agentId = agentId
        self.messageId = messageId
        self.direction = direction
    }
}

// MARK: - Attachment

/// Mesaj ek dosyasi.
struct WebSocketMessageAttachment: Codable, Sendable {
    let type: String
    let url: String
    let mimeType: String
    let sizeBytes: Int

    enum CodingKeys: String, CodingKey {
        case type
        case url
        case mimeType = "mime_type"
        case sizeBytes = "size_bytes"
    }
}

// MARK: - Content Types

/// Baglanti onay mesaji icerigi.
struct ConnectionAckContent: Codable, Sendable {
    let userId: String
    let sessionId: String
    let serverTime: String

    enum CodingKeys: String, CodingKey {
        case userId = "user_id"
        case sessionId = "session_id"
        case serverTime = "server_time"
    }
}

/// AI text response icerigi (backend'den gelen cevap).
struct TextResponseContent: Codable, Sendable {
    let text: String
    let modelUsed: String?
    let tokensUsed: TokenUsage?

    enum CodingKeys: String, CodingKey {
        case text
        case modelUsed = "model_used"
        case tokensUsed = "tokens_used"
    }
}

/// Token kullanim bilgileri.
struct TokenUsage: Codable, Sendable {
    let input: Int
    let output: Int
}

/// Hata mesaj icerigi.
struct ErrorMessageContent: Codable, Sendable {
    let errorCode: String
    let message: String
    let recoverable: Bool
    let details: String?
    let suggestion: String?

    enum CodingKeys: String, CodingKey {
        case errorCode = "error_code"
        case message
        case recoverable
        case details
        case suggestion
    }
}

/// Ilerleme mesaj icerigi.
struct ProgressMessageContent: Codable, Sendable {
    let task: String
    let step: Int
    let totalSteps: Int
    let percentage: Int
    let details: String?
    let phase: String?
    let stepsDetail: [ProgressStepDetailContent]?

    enum CodingKeys: String, CodingKey {
        case task
        case step
        case totalSteps = "total_steps"
        case percentage
        case details
        case phase
        case stepsDetail = "steps_detail"
    }
}

/// Detayli ilerleme adimi icerigi.
struct ProgressStepDetailContent: Codable, Sendable {
    let id: String
    let stepType: String
    let label: String
    let status: String
    let toolName: String?
    let durationSeconds: Double?
    let detail: String?

    enum CodingKeys: String, CodingKey {
        case id
        case stepType = "step_type"
        case label
        case status
        case toolName = "tool_name"
        case durationSeconds = "duration_seconds"
        case detail
    }
}

/// Heartbeat (ping/pong) icerigi.
struct HeartbeatContent: Codable, Sendable {
    let timestamp: String

    init(timestamp: String = ISO8601DateFormatter().string(from: Date())) {
        self.timestamp = timestamp
    }
}

/// Streaming text delta icerigi.
struct ChatStreamContent: Codable, Sendable {
    let messageId: String
    let delta: String
    let index: Int

    enum CodingKeys: String, CodingKey {
        case messageId = "message_id"
        case delta
        case index
    }
}

/// Stream tamamlanma icerigi.
struct ChatStreamEndContent: Codable, Sendable {
    let messageId: String
    let fullText: String
    let modelUsed: String
    let tokensUsed: TokenUsage?

    enum CodingKeys: String, CodingKey {
        case messageId = "message_id"
        case fullText = "full_text"
        case modelUsed = "model_used"
        case tokensUsed = "tokens_used"
    }
}

/// Code diff satiri icerigi.
struct CodeDiffLineContent: Codable, Sendable {
    let type: String
    let content: String
    let lineNumberOld: Int?
    let lineNumberNew: Int?

    enum CodingKeys: String, CodingKey {
        case type
        case content
        case lineNumberOld = "line_number_old"
        case lineNumberNew = "line_number_new"
    }
}

/// Dosya diff icerigi.
struct CodeDiffFileContent: Codable, Sendable {
    let filePath: String
    let isNewFile: Bool?
    let isDeleted: Bool?
    let additions: Int
    let deletions: Int
    let lines: [CodeDiffLineContent]

    enum CodingKeys: String, CodingKey {
        case filePath = "file_path"
        case isNewFile = "is_new_file"
        case isDeleted = "is_deleted"
        case additions
        case deletions
        case lines
    }
}

/// Code diff mesaj icerigi.
struct CodeDiffContent: Codable, Sendable {
    let projectPath: String
    let totalAdditions: Int
    let totalDeletions: Int
    let filesChanged: Int
    let files: [CodeDiffFileContent]

    enum CodingKeys: String, CodingKey {
        case projectPath = "project_path"
        case totalAdditions = "total_additions"
        case totalDeletions = "total_deletions"
        case filesChanged = "files_changed"
        case files
    }
}

/// Proaktif oneri mesaj icerigi.
struct SuggestionContent: Codable, Sendable {
    let messageId: String
    let suggestions: [String]

    enum CodingKeys: String, CodingKey {
        case messageId = "message_id"
        case suggestions
    }
}

/// GitHub webhook event ozeti (broadcast payload).
struct GitHubEventSummaryPayload: Codable, Sendable {
    let number: Int?
    let title: String?
    let url: String?
    let merged: Bool?
    let sender: String?
    let branch: String?
    let commitCount: Int?
    let headMessage: String?
    let pusher: String?

    enum CodingKeys: String, CodingKey {
        case number
        case title
        case url
        case merged
        case sender
        case branch
        case commitCount = "commit_count"
        case headMessage = "head_message"
        case pusher
    }

    init(
        number: Int? = nil, title: String? = nil, url: String? = nil,
        merged: Bool? = nil, sender: String? = nil, branch: String? = nil,
        commitCount: Int? = nil, headMessage: String? = nil, pusher: String? = nil
    ) {
        self.number = number
        self.title = title
        self.url = url
        self.merged = merged
        self.sender = sender
        self.branch = branch
        self.commitCount = commitCount
        self.headMessage = headMessage
        self.pusher = pusher
    }
}

/// GitHub webhook event broadcast mesaj icerigi.
struct GitHubEventPayload: Codable, Sendable {
    let event: String
    let action: String
    let repo: String
    let summary: GitHubEventSummaryPayload
}

/// Task durum guncelleme mesaj icerigi.
/// Backend (Pydantic) snake_case JSON gonderiyor; iOS Swift camelCase mapping yapilir.
/// Doc 10 §6.3.1 — `keyNotFound(taskId)` hatasi bu CodingKeys ile cozulur.
struct TaskStatusContent: Codable, Sendable {
    let taskId: String
    let status: String
    let currentStep: String?
    let progressPct: Int
    let completedSteps: Int
    let totalSteps: Int
    let detail: String?

    enum CodingKeys: String, CodingKey {
        case taskId = "task_id"
        case status
        case currentStep = "current_step"
        case progressPct = "progress_pct"
        case completedSteps = "completed_steps"
        case totalSteps = "total_steps"
        case detail
    }
}

/// Agent durum degisikligi broadcast mesaj icerigi.
struct AgentStatusChangePayload: Codable, Sendable {
    let hostId: String
    let status: String
    let reason: String?
    let isNew: Bool?

    enum CodingKeys: String, CodingKey {
        case hostId = "host_id"
        case status
        case reason
        case isNew = "is_new"
    }
}

// MARK: - Claude Agent Teams Content (T1.6)

/// `session.init` mesaj icerigi. Bridge stream-json `system/init` event'inden uretilir.
/// Kontrat: `apps/backend/app/schemas/messages.py::SessionInitPayload`.
public struct SessionInitContent: Codable, Sendable, Equatable {
    public let sessionId: String
    public let model: String
    public let permissionMode: String
    public let apiKeySource: String
    public let cwd: String
    public let agentTeamsEnabled: Bool
    public let initializedAt: Date

    enum CodingKeys: String, CodingKey {
        case sessionId = "session_id"
        case model
        case permissionMode = "permission_mode"
        case apiKeySource = "api_key_source"
        case cwd
        case agentTeamsEnabled = "agent_teams_enabled"
        case initializedAt = "initialized_at"
    }
}

/// `subagent.spawned` mesaj icerigi.
/// Kontrat: `apps/backend/app/schemas/messages.py::SubagentSpawnedPayload`.
public struct SubagentSpawnedContent: Codable, Sendable, Equatable {
    public let taskId: String
    public let name: String
    public let description: String?
    public let promptPreview: String
    public let subagentType: String?
    public let isolation: String?
    public let startedAt: Date

    enum CodingKeys: String, CodingKey {
        case taskId = "task_id"
        case name
        case description
        case promptPreview = "prompt_preview"
        case subagentType = "subagent_type"
        case isolation
        case startedAt = "started_at"
    }
}

/// `subagent.progress` mesaj icerigi.
/// Kontrat: `apps/backend/app/schemas/messages.py::SubagentProgressPayload`.
public struct SubagentProgressContent: Codable, Sendable, Equatable {
    public let taskId: String
    public let status: String
    public let activity: String
    public let updatedAt: Date

    enum CodingKeys: String, CodingKey {
        case taskId = "task_id"
        case status
        case activity
        case updatedAt = "updated_at"
    }
}

/// `subagent.completed` mesaj icerigi.
/// Kontrat: `apps/backend/app/schemas/messages.py::SubagentCompletedPayload`.
public struct SubagentCompletedContent: Codable, Sendable, Equatable {
    public let taskId: String
    public let status: String
    public let summary: String?
    public let totalTokens: Int
    public let toolUses: Int
    public let durationMs: Int
    public let completedAt: Date

    enum CodingKeys: String, CodingKey {
        case taskId = "task_id"
        case status
        case summary
        case totalTokens = "total_tokens"
        case toolUses = "tool_uses"
        case durationMs = "duration_ms"
        case completedAt = "completed_at"
    }
}

/// `rate_limit.info` mesaj icerigi.
/// Kontrat: `apps/backend/app/schemas/messages.py::RateLimitInfoPayload`.
public struct RateLimitInfoContent: Codable, Sendable, Equatable {
    public let status: String
    public let rateLimitType: String
    public let resetsAt: Int
    public let overageStatus: String
    public let isUsingOverage: Bool

    enum CodingKeys: String, CodingKey {
        case status
        case rateLimitType = "rate_limit_type"
        case resetsAt = "resets_at"
        case overageStatus = "overage_status"
        case isUsingOverage = "is_using_overage"
    }
}

/// `session.title` mesaj icerigi (storage watcher `ai-title`).
/// Kontrat: `apps/backend/app/schemas/messages.py::SessionTitlePayload`.
/// `sessionId` backend Pydantic `UUID` tipinde — Foundation.UUID kullan
/// (T1.5 reviewer notu, contract drift onleme).
public struct SessionTitleContent: Codable, Sendable, Equatable {
    public let sessionId: UUID
    public let aiTitle: String
    public let generatedAt: Date

    enum CodingKeys: String, CodingKey {
        case sessionId = "session_id"
        case aiTitle = "ai_title"
        case generatedAt = "generated_at"
    }
}

/// `session.pr_opened` mesaj icerigi (storage watcher `pr-link`).
/// Kontrat: `apps/backend/app/schemas/messages.py::SessionPrOpenedPayload`.
/// `sessionId` backend Pydantic `UUID` tipinde — Foundation.UUID kullan
/// (T1.5 reviewer notu, contract drift onleme).
public struct SessionPrOpenedContent: Codable, Sendable, Equatable {
    public let sessionId: UUID
    public let prNumber: Int
    public let prUrl: String
    public let prRepository: String
    public let openedAt: Date

    enum CodingKeys: String, CodingKey {
        case sessionId = "session_id"
        case prNumber = "pr_number"
        case prUrl = "pr_url"
        case prRepository = "pr_repository"
        case openedAt = "opened_at"
    }
}

/// `usage.report` mesaj icerigi — 5h + 7d Claude Code subscription kotalari.
/// Kontrat: `apps/backend/app/schemas/messages.py::UsageReportPayload`.
/// Tum zaman alanlari unix timestamp (saniye).
public struct UsageReportContent: Codable, Sendable, Equatable {
    public let fiveHourPct: Int
    public let sevenDayPct: Int
    public let fiveHourResetsAt: Int
    public let sevenDayResetsAt: Int
    public let reportedAt: Int

    enum CodingKeys: String, CodingKey {
        case fiveHourPct = "five_hour_pct"
        case sevenDayPct = "seven_day_pct"
        case fiveHourResetsAt = "five_hour_resets_at"
        case sevenDayResetsAt = "seven_day_resets_at"
        case reportedAt = "reported_at"
    }
}

// MARK: - Message Factory

/// WebSocket mesaj olusturma yardimci fonksiyonlari.
enum WebSocketMessageFactory {

    /// Metin mesaji olusturur.
    static func textMessage(
        _ text: String,
        sessionId: String? = nil,
        projectId: String? = nil,
        agentId: String? = nil
    ) -> WebSocketBaseMessage {
        WebSocketBaseMessage(
            type: WebSocketMessageType.text.rawValue,
            content: .text(text),
            metadata: WebSocketMessageMetadata(
                sessionId: sessionId,
                projectId: projectId,
                agentId: agentId,
                direction: WebSocketMessageDirection.clientToServer.rawValue
            )
        )
    }

    /// Ping mesaji olusturur.
    static func pingMessage() -> WebSocketBaseMessage {
        WebSocketBaseMessage(
            type: WebSocketMessageType.ping.rawValue,
            content: .heartbeat(HeartbeatContent())
        )
    }

    /// Pong mesaji olusturur.
    static func pongMessage() -> WebSocketBaseMessage {
        WebSocketBaseMessage(
            type: WebSocketMessageType.pong.rawValue,
            content: .heartbeat(HeartbeatContent())
        )
    }

    /// Aktif stream'i iptal etmek icin mesaj olusturur.
    static func cancelStreamMessage(sessionId: String? = nil) -> WebSocketBaseMessage {
        WebSocketBaseMessage(
            type: WebSocketMessageType.cancelStream.rawValue,
            metadata: WebSocketMessageMetadata(
                sessionId: sessionId,
                direction: WebSocketMessageDirection.clientToServer.rawValue
            )
        )
    }
}
