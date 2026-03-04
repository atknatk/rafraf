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
}

/// Mesaj yonu.
enum WebSocketMessageDirection: String, Codable, Sendable {
    case clientToServer = "client_to_server"
    case serverToClient = "server_to_client"
}

// MARK: - Base Message

/// Temel WebSocket mesaj yapisi.
/// Tum mesajlar bu yapiya uygun encode/decode edilir.
struct WebSocketBaseMessage: Codable, Sendable {
    let id: String
    let type: String
    let content: WebSocketContent?
    let metadata: WebSocketMessageMetadata?
    let attachments: [WebSocketMessageAttachment]?

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
        }
    }
}

// MARK: - Metadata

/// Mesaj metadata bilgileri.
struct WebSocketMessageMetadata: Codable, Sendable {
    let timestamp: String
    let sessionId: String?
    let projectId: String?
    let messageId: String?
    let direction: String

    init(
        timestamp: String = ISO8601DateFormatter().string(from: Date()),
        sessionId: String? = nil,
        projectId: String? = nil,
        messageId: String? = nil,
        direction: String = WebSocketMessageDirection.clientToServer.rawValue
    ) {
        self.timestamp = timestamp
        self.sessionId = sessionId
        self.projectId = projectId
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

// MARK: - Message Factory

/// WebSocket mesaj olusturma yardimci fonksiyonlari.
enum WebSocketMessageFactory {

    /// Metin mesaji olusturur.
    static func textMessage(
        _ text: String,
        sessionId: String? = nil,
        projectId: String? = nil
    ) -> WebSocketBaseMessage {
        WebSocketBaseMessage(
            type: WebSocketMessageType.text.rawValue,
            content: .text(text),
            metadata: WebSocketMessageMetadata(
                sessionId: sessionId,
                projectId: projectId,
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
