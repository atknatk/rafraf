import Foundation
import os

/// Onay repository implementasyonu.
/// WebSocket uzerinden onay kararlarini backend'e gonderir.
///
/// V1.x SHIP BLOCKER fix — application-layer ACK + retry:
/// - Her gonderim benzersiz `client_message_id` ile metadata'ya iliştirilir.
/// - Gonderim sonrasi `ackTimeout` boyunca backend ack envelope beklenir.
/// - Ack alinmazsa `deliveryChannel.forceReconnect()` cagirilip BIR kez retry
///   denenir. Ikinci deneme de basarisiz olursa `WebSocketError.deliveryFailed`
///   firlatilir (kullaniciya "tekrar dene" gostermek icin).
final class ApprovalRepositoryImpl: ApprovalRepositoryProtocol, @unchecked Sendable {
    private let deliveryChannel: ApprovalDeliveryChannel
    private let messageRouter: WebSocketMessageRouter
    private let ackTimeout: Duration
    private let logger = AppLogger.logger(for: "Approval")

    /// V1.x ship blocker fix init — production DI ve testler bu init'i kullanir.
    /// - Parameters:
    ///   - deliveryChannel: Soyutlanmis WebSocket gonderim kanali
    ///     (production'da `WebSocketClient` adapter'i; testte mock).
    ///   - messageRouter: Wire encoding icin paylasilan router.
    ///   - ackTimeout: Backend ack icin maksimum bekleme suresi
    ///     (default: 3s — heartbeat 30s'den cok daha kisa, kullanici 3s'de
    ///     "donmus mu?" diye dusunmeden retry tamamlanir).
    init(
        deliveryChannel: ApprovalDeliveryChannel,
        messageRouter: WebSocketMessageRouter,
        ackTimeout: Duration = .seconds(3)
    ) {
        self.deliveryChannel = deliveryChannel
        self.messageRouter = messageRouter
        self.ackTimeout = ackTimeout
    }

    /// Geriye-uyumluluk init'i. Mevcut DI cagirimi (Factory) ApprovalRepositoryImpl'i
    /// `WebSocketClient + WebSocketMessageRouter` ile insa eder; bu init istenen
    /// adapter'i sarar.
    ///
    /// `ackInbox` PARAMETRE ZORUNLU (default YOK): default deger, yeni bir
    /// inbox uretip ack handler ile baglantisini kopararak SHIP BLOCKER
    /// bug'ini sessizce geri getirebilir. Caller (AppContainer DI) singleton
    /// inbox'i acikca gecmek ZORUNDA.
    convenience init(
        webSocketClient: WebSocketClient,
        messageRouter: WebSocketMessageRouter,
        ackInbox: ApprovalDeliveryAckInbox
    ) {
        let adapter = WebSocketClientApprovalDeliveryAdapter(
            client: webSocketClient,
            inbox: ackInbox
        )
        self.init(
            deliveryChannel: adapter,
            messageRouter: messageRouter,
            ackTimeout: .seconds(3)
        )
    }

    func submitDecision(
        approvalId: String,
        decision: ApprovalDecision,
        note: String?
    ) async throws {
        let responseDTO = ApprovalMapper.toResponseDTO(
            approvalId: approvalId,
            decision: decision,
            note: note
        )

        // V1.x ship blocker fix: her gonderim icin benzersiz client_message_id
        // uretilir. Retry ayni id ile gider — backend dedup ve audit korelasyonu.
        let clientMessageId = UUID().uuidString

        let message = WebSocketBaseMessage(
            type: "approval_response",
            content: .approvalResponse(responseDTO),
            metadata: WebSocketMessageMetadata(
                direction: WebSocketMessageDirection.clientToServer.rawValue,
                clientMessageId: clientMessageId
            )
        )

        let jsonString = try await messageRouter.encode(message)

        logger.info(
            "approval_response gonderiliyor approvalId=\(approvalId, privacy: .public) clientMessageId=\(clientMessageId, privacy: .public) decision=\(String(describing: decision), privacy: .public)"
        )

        // Adim 1: ilk gonderim denemesi (send + ack bekle).
        do {
            try await sendAndAwaitAck(envelope: jsonString, clientMessageId: clientMessageId)
            logger.info("approval_response teslim onaylandi (ilk denemede) clientMessageId=\(clientMessageId, privacy: .public)")
            return
        } catch let error as WebSocketError {
            // Sadece teslim guvencesi ile ilgili hatalar retry'a girer.
            // Diger WebSocketError'lar (ornek: invalidData) repository'nin
            // upper layer'a duz iletmesi gerekir.
            switch error {
            case .deliveryTimeout, .notConnected, .connectionFailed, .heartbeatTimeout:
                logger.warning(
                    "approval_response ilk denemede teslim edilemedi (\(String(describing: error), privacy: .public)) — forceReconnect + 1x retry clientMessageId=\(clientMessageId, privacy: .public)"
                )
            default:
                throw error
            }
        }

        // Adim 2: forceReconnect — baglanti tamamlanmadan retry'i bilerek
        // baslatma; aksi halde her retry `notConnected` ile patlayip
        // sessizce `deliveryFailed`'e map edilir (V1.x reviewer bulgusu #2).
        do {
            try await deliveryChannel.forceReconnect()
        } catch {
            logger.error(
                "forceReconnect basarisiz clientMessageId=\(clientMessageId, privacy: .public) error=\(String(describing: error), privacy: .public) — deliveryFailed"
            )
            throw WebSocketError.deliveryFailed
        }

        do {
            // Adim 3: retry — ayni envelope, ayni clientMessageId (backend
            // dedup ve audit korelasyonu icin).
            try await sendAndAwaitAck(envelope: jsonString, clientMessageId: clientMessageId)
            logger.info("approval_response teslim onaylandi (retry sonrasi) clientMessageId=\(clientMessageId, privacy: .public)")
            return
        } catch {
            // Adim 4: ikinci deneme de basarisiz — kullaniciya geri bildirim
            // sart, sessiz kayip yasak.
            logger.error(
                "approval_response retry sonrasi da teslim edilemedi clientMessageId=\(clientMessageId, privacy: .public) error=\(String(describing: error), privacy: .public)"
            )
            throw WebSocketError.deliveryFailed
        }
    }

    /// Bir kez send + ack bekle. Send hata atarsa `WebSocketError`,
    /// ack timeout'da `WebSocketError.deliveryTimeout` atar.
    private func sendAndAwaitAck(envelope: String, clientMessageId: String) async throws {
        try await deliveryChannel.send(envelope: envelope, clientMessageId: clientMessageId)
        try await deliveryChannel.awaitAck(clientMessageId: clientMessageId, timeout: ackTimeout)
    }
}

/// `ApprovalDeliveryChannel`'in production WebSocketClient adapter'i.
///
/// - `send` → `WebSocketClient.send(envelope)` cagirir; tum hatalari
///   propagate eder.
/// - `awaitAck` → `inbox.awaitAck(...)` delege eder.
/// - `forceReconnect` → `WebSocketClient.forceReconnect()` cagirir.
final class WebSocketClientApprovalDeliveryAdapter: ApprovalDeliveryChannel, @unchecked Sendable {
    private let client: WebSocketClient
    private let inbox: ApprovalDeliveryAckInbox

    init(client: WebSocketClient, inbox: ApprovalDeliveryAckInbox) {
        self.client = client
        self.inbox = inbox
    }

    func send(envelope: String, clientMessageId: String) async throws {
        // Wire-encoded JSON string'i WebSocketClient'a teslim et.
        // Hatalar (ornek: notConnected) repository'ye dogrudan iletilir.
        try await client.send(envelope)
    }

    func awaitAck(clientMessageId: String, timeout: Duration) async throws {
        try await inbox.awaitAck(clientMessageId: clientMessageId, timeout: timeout)
    }

    func forceReconnect() async throws {
        try await client.forceReconnect()
    }
}

/// Approval repository hatalari.
enum ApprovalRepositoryError: Error, Sendable {
    case encodingFailed
    case sendFailed
}
