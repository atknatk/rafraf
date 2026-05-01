import Foundation
import os

/// WebSocket mesaj handler protokolu.
/// Her mesaj tipi icin bir handler implement edilir.
protocol WebSocketMessageHandler: Sendable {
    /// Mesaji isle ve sonuc dondur.
    func handle(_ message: WebSocketBaseMessage) async
}

/// WebSocket mesaj yonlendirici.
/// Gelen mesajlari `type` field'ina gore ilgili handler'a yonlendirir.
actor WebSocketMessageRouter {
    private var handlers: [String: WebSocketMessageHandler] = [:]
    private let decoder: JSONDecoder
    private let encoder: JSONEncoder
    private let logger = Logger(
        subsystem: "com.rafraf",
        category: "WebSocketMessageRouter"
    )

    /// WebSocketClient tarafindan dogrudan islenen dahili mesaj tipleri.
    /// Bu tipler icin handler kaydi gerekmez.
    private let builtInTypes: Set<String> = [
        "ping", "pong", "connection_ack"
    ]

    /// Claude Agent Teams WS mesaj tipleri (T1.6).
    /// Bu tipler icin shipping handler'lar T1.7 (subagent tree)
    /// ve T1.8 (usage gauge) tarafindan eklenecek. Su an icin
    /// log icin builtInTypes'a benzer bir alanda tutulurlar.
    private let agentTeamsTypes: Set<String> = [
        WebSocketMessageType.sessionInit.rawValue,
        WebSocketMessageType.subagentSpawned.rawValue,
        WebSocketMessageType.subagentProgress.rawValue,
        WebSocketMessageType.subagentCompleted.rawValue,
        WebSocketMessageType.rateLimitInfo.rawValue,
        WebSocketMessageType.sessionTitle.rawValue,
        WebSocketMessageType.sessionPrOpened.rawValue,
        WebSocketMessageType.usageReport.rawValue
    ]

    init() {
        let jsonDecoder = JSONDecoder()
        // NOTE: keyDecodingStrategy = .convertFromSnakeCase YASAK — her Content struct'inin
        // explicit snake_case CodingKeys raw value'lari mevcut. Strategy uygulanirsa JSON
        // key'leri once camelCase'e cevrilir ve CodingKeys raw value'lari ile eslesmez
        // (sessizce keyNotFound → try? swallows → content nil). T0.6 (TaskStatusContent)
        // tasarim niyeti: explicit CodingKeys = tek dogru kontrat kaynagi.
        // Backend (Pydantic) ISO8601 datetime serileştirir; Mac bridge ise mikrosaniyeli
        // veya offset'siz olabilir. Esnek bir tarih decoder'i ile her iki bicimi destekle.
        jsonDecoder.dateDecodingStrategy = .custom { decoder in
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
        self.decoder = jsonDecoder

        let jsonEncoder = JSONEncoder()
        // NOTE: keyEncodingStrategy = .convertToSnakeCase YASAK — decoder ile simetri icin
        // ayni kural; explicit CodingKeys snake_case wire format kontratidir.
        jsonEncoder.dateEncodingStrategy = .iso8601
        self.encoder = jsonEncoder
    }

    /// Belirtilen mesaj tipi icin handler kaydeder.
    /// - Parameters:
    ///   - type: Mesaj tipi (ornek: "text", "connection_ack")
    ///   - handler: Mesaji isleyecek handler
    func register(type: String, handler: WebSocketMessageHandler) {
        handlers[type] = handler
        logger.info("Handler kaydedildi: \(type)")
    }

    /// Belirtilen mesaj tipinin handler'ini kaldirir.
    /// - Parameter type: Kaldirilacak mesaj tipi
    func unregister(type: String) {
        handlers.removeValue(forKey: type)
        logger.info("Handler kaldirildi: \(type)")
    }

    /// Gelen JSON mesajini decode eder ve ilgili handler'a yonlendirir.
    /// - Parameter jsonString: JSON formatinda mesaj string'i
    /// - Returns: Decode edilen mesaj (handler yoksa da doner)
    @discardableResult
    func route(_ jsonString: String) async throws -> WebSocketBaseMessage {
        guard let data = jsonString.data(using: .utf8) else {
            logger.error("Mesaj UTF-8 decode edilemedi")
            throw WebSocketMessageRouterError.invalidEncoding
        }

        let message: WebSocketBaseMessage
        do {
            message = try decoder.decode(WebSocketBaseMessage.self, from: data)
        } catch {
            logger.error("Mesaj JSON decode edilemedi: \(error.localizedDescription)")
            throw WebSocketMessageRouterError.decodingFailed(error)
        }

        logger.debug("Mesaj alindi - type: \(message.type), id: \(message.id)")

        if let handler = handlers[message.type] {
            await handler.handle(message)
        } else if agentTeamsTypes.contains(message.type) {
            // T1.6: Agent Teams mesajlari decode olur ama henuz UI handler'i yok.
            // T1.7 (subagent tree) ve T1.8 (usage gauge) bu tiplere handler kaydedecek.
            logAgentTeamsMessageReceived(message)
        } else if !builtInTypes.contains(message.type) {
            logger.warning("Handler bulunamadi: \(message.type)")
        }

        return message
    }

    /// Agent Teams mesajlarinin alindiginin loglanmasi — handler eklenene kadar
    /// gorunmeden kaybolmamalari icin.
    private func logAgentTeamsMessageReceived(_ message: WebSocketBaseMessage) {
        switch message.type {
        case WebSocketMessageType.sessionInit.rawValue:
            // TODO(T1.7): SessionInitContent handler ekle (Home/Agent feature).
            logger.info("session.init alindi (handler bekleniyor): \(message.id)")
        case WebSocketMessageType.subagentSpawned.rawValue:
            // T1.7: SubagentSpawnedHandler app start'ta register edilir
            // (ContentView.registerSubagentHandlers). Bu log fallback'i sadece
            // handler register edilmediginde (ornek: arka planda erken mesaj)
            // gorunur — operasyonel debug icin tutuluyor.
            logger.info("subagent.spawned alindi (handler henuz register degil): \(message.id)")
        case WebSocketMessageType.subagentProgress.rawValue:
            // T1.7: SubagentProgressHandler app start'ta register edilir.
            logger.info("subagent.progress alindi (handler henuz register degil): \(message.id)")
        case WebSocketMessageType.subagentCompleted.rawValue:
            // T1.7: SubagentCompletedHandler app start'ta register edilir.
            logger.info("subagent.completed alindi (handler henuz register degil): \(message.id)")
        case WebSocketMessageType.rateLimitInfo.rawValue:
            // TODO(T1.8): RateLimitInfoContent → kullanici uyarisi / banner.
            logger.info("rate_limit.info alindi (handler bekleniyor): \(message.id)")
        case WebSocketMessageType.sessionTitle.rawValue:
            // T1.8: Handler kaydedilmedigi takdirde dusen log.
            // Normal akista `SessionTitleMessageHandler` (Home feature) handler
            // olarak kayitli oldugu icin bu branch'e dusulmez.
            logger.info("session.title alindi (handler bekleniyor): \(message.id)")
        case WebSocketMessageType.sessionPrOpened.rawValue:
            // TODO(T1.7): SessionPrOpenedContent → PR linki UI.
            logger.info("session.pr_opened alindi (handler bekleniyor): \(message.id)")
        case WebSocketMessageType.usageReport.rawValue:
            // TODO(T1.8): UsageReportContent → RFUsageGauge guncelleme.
            logger.info("usage.report alindi (handler bekleniyor): \(message.id)")
        default:
            break
        }
    }

    /// WebSocket mesajini JSON string'e encode eder.
    /// - Parameter message: Encode edilecek mesaj
    /// - Returns: JSON string
    func encode(_ message: WebSocketBaseMessage) throws -> String {
        let data = try encoder.encode(message)
        guard let jsonString = String(data: data, encoding: .utf8) else {
            throw WebSocketMessageRouterError.encodingFailed
        }
        return jsonString
    }
}

/// WebSocket mesaj yonlendirme hatalari.
enum WebSocketMessageRouterError: Error, Sendable {
    case invalidEncoding
    case decodingFailed(Error)
    case encodingFailed
    case handlerNotFound(String)
}

/// Esnek ISO8601 tarih ayristirici — Pydantic mikrosaniyeli, offset'siz veya
/// "Z" sonlu cikti uretebilir. Bu yardimci hepsini dener.
enum WebSocketISODateParser {
    // SAFETY: Apple guarantees DateFormatter / ISO8601DateFormatter are thread-safe after init; do not mutate after the closure returns.
    nonisolated(unsafe) private static let withFractionalSeconds: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter
    }()

    // SAFETY: Apple guarantees DateFormatter / ISO8601DateFormatter are thread-safe after init; do not mutate after the closure returns.
    nonisolated(unsafe) private static let standard: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        return formatter
    }()

    /// Pydantic `datetime.isoformat()` ciktisi gibi offset'siz tarih bicimi
    /// (ornek: `2026-04-02T12:34:56.789012`).
    // SAFETY: Apple guarantees DateFormatter / ISO8601DateFormatter are thread-safe after init; do not mutate after the closure returns.
    nonisolated(unsafe) private static let pydanticNaive: DateFormatter = {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(identifier: "UTC")
        formatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss.SSSSSS"
        return formatter
    }()

    // SAFETY: Apple guarantees DateFormatter / ISO8601DateFormatter are thread-safe after init; do not mutate after the closure returns.
    nonisolated(unsafe) private static let pydanticNaiveNoFraction: DateFormatter = {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(identifier: "UTC")
        formatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
        return formatter
    }()

    static func parse(_ raw: String) -> Date? {
        if let date = withFractionalSeconds.date(from: raw) {
            return date
        }
        if let date = standard.date(from: raw) {
            return date
        }
        if let date = pydanticNaive.date(from: raw) {
            return date
        }
        if let date = pydanticNaiveNoFraction.date(from: raw) {
            return date
        }
        return nil
    }
}
