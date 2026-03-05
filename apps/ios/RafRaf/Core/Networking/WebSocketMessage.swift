import Foundation

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
    // Voice conversation types
    case voiceAudioChunk = "voice.audio_chunk"
    case voiceAudioEnd = "voice.audio_end"
    case voiceInterrupt = "voice.interrupt"
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
    case voiceAudioChunk(VoiceAudioChunkContent)
    case voiceAudioEnd(VoiceAudioEndContent)
    case codeDiff(CodeDiffContent)
    case suggestion(SuggestionContent)
    case githubEvent(GitHubEventPayload)
    case agentStatusChange(AgentStatusChangePayload)

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

        if let audioChunk = try? container.decode(VoiceAudioChunkContent.self) {
            self = .voiceAudioChunk(audioChunk)
            return
        }

        if let audioEnd = try? container.decode(VoiceAudioEndContent.self) {
            self = .voiceAudioEnd(audioEnd)
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
        case .voiceAudioChunk(let value):
            try container.encode(value)
        case .voiceAudioEnd(let value):
            try container.encode(value)
        case .codeDiff(let value):
            try container.encode(value)
        case .suggestion(let value):
            try container.encode(value)
        case .githubEvent(let value):
            try container.encode(value)
        case .agentStatusChange(let value):
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
}

// MARK: - Content Types

/// Baglanti onay mesaji icerigi.
struct ConnectionAckContent: Codable, Sendable {
    let userId: String
    let sessionId: String
    let serverTime: String
}

/// AI text response icerigi (backend'den gelen cevap).
struct TextResponseContent: Codable, Sendable {
    let text: String
    let modelUsed: String?
    let tokensUsed: TokenUsage?
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
}

/// Stream tamamlanma icerigi.
struct ChatStreamEndContent: Codable, Sendable {
    let messageId: String
    let fullText: String
    let modelUsed: String
    let tokensUsed: TokenUsage?
}

/// TTS ses chunk icerigi.
struct VoiceAudioChunkContent: Codable, Sendable {
    let messageId: String
    let chunkIndex: Int
    let audioData: String  // base64-encoded MP3
    let sentenceText: String
    let isLastChunk: Bool
}

/// Ses akisi tamamlanma icerigi.
struct VoiceAudioEndContent: Codable, Sendable {
    let messageId: String
}

/// Code diff satiri icerigi.
struct CodeDiffLineContent: Codable, Sendable {
    let type: String
    let content: String
    let lineNumberOld: Int?
    let lineNumberNew: Int?
}

/// Dosya diff icerigi.
struct CodeDiffFileContent: Codable, Sendable {
    let filePath: String
    let isNewFile: Bool?
    let isDeleted: Bool?
    let additions: Int
    let deletions: Int
    let lines: [CodeDiffLineContent]
}

/// Code diff mesaj icerigi.
struct CodeDiffContent: Codable, Sendable {
    let projectPath: String
    let totalAdditions: Int
    let totalDeletions: Int
    let filesChanged: Int
    let files: [CodeDiffFileContent]
}

/// Proaktif oneri mesaj icerigi.
struct SuggestionContent: Codable, Sendable {
    let messageId: String
    let suggestions: [String]
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

/// Agent durum degisikligi broadcast mesaj icerigi.
struct AgentStatusChangePayload: Codable, Sendable {
    let hostId: String
    let status: String
    let reason: String?
    let isNew: Bool?
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

    /// Sesli mesaj (transcribed text) olusturur.
    static func voiceMessage(
        _ text: String,
        sessionId: String? = nil
    ) -> WebSocketBaseMessage {
        WebSocketBaseMessage(
            type: "voice",
            content: .text(text),
            metadata: WebSocketMessageMetadata(
                sessionId: sessionId,
                direction: WebSocketMessageDirection.clientToServer.rawValue
            )
        )
    }

    /// Voice interrupt (barge-in) mesaji olusturur.
    static func voiceInterruptMessage(
        sessionId: String? = nil
    ) -> WebSocketBaseMessage {
        WebSocketBaseMessage(
            type: WebSocketMessageType.voiceInterrupt.rawValue,
            metadata: WebSocketMessageMetadata(
                sessionId: sessionId,
                direction: WebSocketMessageDirection.clientToServer.rawValue
            )
        )
    }
}
