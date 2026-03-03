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
    case connectionAck(ConnectionAckContent)
    case error(ErrorMessageContent)
    case progress(ProgressMessageContent)
    case heartbeat(HeartbeatContent)

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()

        if let text = try? container.decode(String.self) {
            self = .text(text)
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
        case .connectionAck(let value):
            try container.encode(value)
        case .error(let value):
            try container.encode(value)
        case .progress(let value):
            try container.encode(value)
        case .heartbeat(let value):
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
}
