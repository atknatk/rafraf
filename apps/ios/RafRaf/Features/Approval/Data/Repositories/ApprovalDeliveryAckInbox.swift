import Foundation

/// V1.x SHIP BLOCKER fix — backend `ack` envelope inbox'i.
///
/// Backend her critical client→server mesaj icin `type: "ack"` envelope yayinlar
/// (`shared/api-contracts/ws/ack-messages.json`). Bu inbox WebSocketMessageRouter
/// tarafindan ack mesajlarini alir, `client_message_id` ile bekleyen
/// continuation'lari resolve eder. `ApprovalDeliveryChannel` production
/// implementasyonu bu inbox'i kullanir.
///
/// SAFETY: actor — birden fazla concurrent send `awaitAck` cagirabilir;
/// continuation map'i thread-safe olmali.
///
/// EARLY-ACK BUFFERING (race fix — REGRESSION RISK YUKSEK, simplifiye etme):
/// `ApprovalRepositoryImpl.sendAndAwaitAck` mantigi gereken sirayla
/// `send → awaitAck` cagirir. Hem production WebSocket hem de testteki mock'ta
/// `send` tamamlanmadan ONCE ack alinabilir:
/// - Production: backend ack envelope'u network'ten cok hizli donerse,
///   WebSocketClient'in receive loop Task'i ack'i `handleAck`'a iletir; bu
///   sirada repository hala `awaitAck` cagrisini henuz yapmamis olabilir.
/// - Mock: `MockApprovalDeliveryChannel.send` icinden senkron olarak ack
///   continuation tetiklenir.
///
/// Eger `handleAck` cagildiginda pending continuation YOKSA ve sessizce
/// donulurse, ack hicbir continuation'a teslim edilmeden dusuyor → `awaitAck`
/// timeout'a kadar bekliyor → kullaniciya `deliveryFailed` olarak yansiyor.
///
/// Cozum: `handleAck` pending bulamazsa id'yi `earlyAcks` set'ine yazar.
/// `awaitAck` register etmeden ONCE bu set'i kontrol eder; varsa hemen donmek
/// suretiyle yarisi cozer.
///
/// Bounded growth: `earlyAcks` en fazla son 100 id'yi tutar — yabanci/never-
/// awaited ack'lerin sinirsiz birikmesini engeller. FIFO eviction
/// (`earlyAcksOrder`).
///
/// CONTINUATION-LEAK SAFETY:
/// `awaitAck` continuation'i actor isolation icinde ATOMIK olarak register
/// edilir (TOCTOU yok — `withCheckedThrowingContinuation` closure'i actor
/// metodunun synchronous body'si icinde calisir, dolayisiyla `pending[...] =
/// cont` yazimi ack/timeout race baslamadan TAMAMEN yerlesir). Timeout
/// `Task.sleep` continuation atandiktan SONRA spawn edilir; hangisi once
/// gelirse `pending.removeValue` ile diger tarafi idempotent sekilde no-op'a
/// dusurur. Hicbir kosulda continuation `pending`'de leak edilmez.
actor ApprovalDeliveryAckInbox {

    /// Pending ack continuation'lari — `client_message_id` ile anahtarli.
    private var pending: [String: CheckedContinuation<Void, Error>] = [:]

    /// Erken gelen ack id'leri (henuz awaitAck cagrilmamis).
    private var earlyAcks: Set<String> = []
    private var earlyAcksOrder: [String] = []
    private let earlyAcksMaxSize = 100

    init() {}

    /// `clientMessageId` icin ack bekler.
    ///
    /// Davranis:
    /// 1. `earlyAcks`'te id varsa hemen tuket ve don.
    /// 2. Yoksa continuation'i actor-atomik olarak `pending`'e yaz.
    /// 3. Continuation register edildikten SONRA timeout Task'ini spawn et;
    ///    handleAck veya timeout — hangisi once gelirse `pending.removeValue`
    ///    ile digerini idempotent sekilde no-op yapar.
    ///
    /// - Throws: `WebSocketError.deliveryTimeout` timeout durumunda.
    func awaitAck(clientMessageId: String, timeout: Duration) async throws {
        try await withCheckedThrowingContinuation { (cont: CheckedContinuation<Void, Error>) in
            // BU CLOSURE actor isolation icinde synchronous calisir
            // (`awaitAck` actor-isolated metod govdesi). pending[...] = cont
            // yazimi rakipsiz tamamlanir; ardindan timeout Task'i spawn edilir.
            // Continuation register edilmeden ONCE timeout race'i baslamiyor —
            // TOCTOU yok.
            if earlyAcks.remove(clientMessageId) != nil {
                if let idx = earlyAcksOrder.firstIndex(of: clientMessageId) {
                    earlyAcksOrder.remove(at: idx)
                }
                cont.resume(returning: ())
                return
            }
            // Ayni id icin onceki continuation varsa (teorik olarak olmamali —
            // her gonderim benzersiz UUID), guvenli sekilde timeout ile cancel
            // edip yenisini yaz. Sessiz drop yok.
            if let existing = pending.removeValue(forKey: clientMessageId) {
                existing.resume(throwing: WebSocketError.deliveryTimeout)
            }
            pending[clientMessageId] = cont

            Task { [weak self] in
                try? await Task.sleep(for: timeout)
                await self?.fireTimeout(clientMessageId: clientMessageId)
            }
        }
    }

    /// Backend ack envelope'i alindiginda WebSocketMessageRouter cagirir.
    /// Bekleyen continuation varsa resume eder; yoksa `earlyAcks`'e yazar.
    func handleAck(clientMessageId: String) {
        if let cont = pending.removeValue(forKey: clientMessageId) {
            cont.resume(returning: ())
            return
        }
        bufferEarlyAck(clientMessageId: clientMessageId)
    }

    /// Test/diagnostic: bekleyen continuation sayisi.
    /// `inboxTimeoutDoesNotLeakContinuation` testi bu sayinin sifirlanmasini
    /// dogrular — leak gozlemi icin tek API.
    func pendingCount() -> Int {
        pending.count
    }

    // MARK: - Private

    /// Timeout Task'inden cagirilir. Idempotent: handleAck zaten cozmusse
    /// `pending.removeValue` nil doner ve no-op olur.
    private func fireTimeout(clientMessageId: String) {
        if let cont = pending.removeValue(forKey: clientMessageId) {
            cont.resume(throwing: WebSocketError.deliveryTimeout)
        }
    }

    /// Erken ack'i FIFO buffer'a yaz; bound asilirsa en eskiyi at.
    private func bufferEarlyAck(clientMessageId: String) {
        guard !earlyAcks.contains(clientMessageId) else { return }
        earlyAcks.insert(clientMessageId)
        earlyAcksOrder.append(clientMessageId)
        while earlyAcksOrder.count > earlyAcksMaxSize {
            let evicted = earlyAcksOrder.removeFirst()
            earlyAcks.remove(evicted)
        }
    }
}
