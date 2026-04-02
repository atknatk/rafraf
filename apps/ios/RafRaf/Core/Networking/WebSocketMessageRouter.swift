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

    init() {
        let jsonDecoder = JSONDecoder()
        jsonDecoder.keyDecodingStrategy = .convertFromSnakeCase
        self.decoder = jsonDecoder

        let jsonEncoder = JSONEncoder()
        jsonEncoder.keyEncodingStrategy = .convertToSnakeCase
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
        } else if !builtInTypes.contains(message.type) {
            logger.warning("Handler bulunamadi: \(message.type)")
        }

        return message
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
