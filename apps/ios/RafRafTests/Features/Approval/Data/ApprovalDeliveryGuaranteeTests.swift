import Foundation
import Testing
@testable import RafRaf

// MARK: - Test Doubles

/// Tek-noktadan kontrollu sahte WebSocket gonderim hatti.
/// `ApprovalRepositoryImpl` icindeki gonderim kanalini soyutlayarak,
/// canli WS olmadan stale-connection senaryolarini taklit eder.
///
/// `nextSendOutcome` kuyrugu sirayla tuketilir:
/// - `.delivered` → `send` basariyla doner ve handshake icin ack uretilir.
/// - `.silentlyDropped` → `send` HATA VERMEDEN doner (buffer'a yazildi sanip,
///   kablo karsisinda kaybolan mesaj). Ack URETILMEZ. Bu, V1.x ship blocker
///   bug'unu birebir taklit eder.
/// - `.failure(error)` → send error firlatir.
actor MockApprovalDeliveryChannel: ApprovalDeliveryChannel {

    enum SendOutcome: Sendable {
        case delivered
        case silentlyDropped
        case failure(WebSocketError)
    }

    /// Gonderilen her mesaj icin alinacak davranis kuyrugu.
    var outcomes: [SendOutcome] = []
    /// Kac kez `send` cagirildi.
    private(set) var sendCallCount = 0
    /// Kac kez `forceReconnect` cagirildi.
    private(set) var reconnectCount = 0
    /// Gonderilen JSON envelope'larin sirayla kaydi (assertion icin).
    private(set) var sentEnvelopes: [String] = []
    /// Bekleyen `awaitAck` continuation'lari.
    private var ackContinuations: [String: CheckedContinuation<Void, Never>] = [:]
    /// EARLY-ACK BUFFER (production `ApprovalDeliveryAckInbox` ile ayni semantic):
    /// `ApprovalRepositoryImpl.sendAndAwaitAck` `send`'i ONCE await ediyor.
    /// Mock'in `send` icindeki `.delivered` ack'i continuation register edilmeden
    /// once tetiklenebiliyor. Sessizce dusurmek yerine buraya yazilir; `awaitAck`
    /// register'dan once buffer'i tuketir, race olmaz.
    private var earlyAcks: Set<String> = []

    /// PRODUCTION-PARITY: WebSocketClient connection state'ini modeller.
    /// `forceReconnect` once false yapar, sonra true'ya doner — bu sayede
    /// `submitDecision` retry path'i "always notConnected" race'ini tetikler
    /// ve gercek production senaryosunu test eder. Default: true (saglikli).
    private var isConnected: Bool = true

    func enqueue(_ outcomes: [SendOutcome]) {
        self.outcomes.append(contentsOf: outcomes)
    }

    /// `ApprovalDeliveryChannel` kontrati.
    func send(envelope: String, clientMessageId: String) async throws {
        sendCallCount += 1

        // PRODUCTION-PARITY: baglanti yoksa send patlar (notConnected).
        // forceReconnect senkron olarak baglantiyi geri verirse bu kosul
        // tetiklenmez; aksi halde retry'in baglanti beklemeyi gerekli
        // kildigi gercek senaryo test edilir.
        guard isConnected else {
            throw WebSocketError.notConnected
        }

        sentEnvelopes.append(envelope)

        let outcome = outcomes.isEmpty ? .delivered : outcomes.removeFirst()
        switch outcome {
        case .delivered:
            // Sahte ack — continuation hazirsa tetikle, degilse buffer'a yaz.
            if let cont = ackContinuations.removeValue(forKey: clientMessageId) {
                cont.resume()
            } else {
                earlyAcks.insert(clientMessageId)
            }
            return
        case .silentlyDropped:
            // Bug yeniden uretimi: HATA VERME ama ack DA URETME.
            return
        case .failure(let err):
            throw err
        }
    }

    /// PRODUCTION-PARITY: forceReconnect baglantiyi once dusurur, sonra
    /// kurar (kontrolu testlere veriyoruz: `nextForceReconnectDoesNotRecover`
    /// olsaydi false birakilirdi — su an default davranis "kurtarir"). Bu
    /// davranis production'in `WebSocketClient.forceReconnect()` semantigine
    /// uyar: metod ancak `.connected`'a tekrar gecince doner.
    var nextForceReconnectShouldFail: Bool = false
    func forceReconnect() async throws {
        reconnectCount += 1
        isConnected = false
        if nextForceReconnectShouldFail {
            throw WebSocketError.connectionFailed("mock forceReconnect failed")
        }
        // Kucuk async hop — production'da reconnect Task scheduling tasklit.
        await Task.yield()
        isConnected = true
    }

    /// `ApprovalDeliveryChannel` kontrati: once `earlyAcks`'i kontrol eder
    /// (race fix), yoksa continuation kaydet ve `delivered` outcome veya
    /// timeout'u bekle.
    func awaitAck(clientMessageId: String, timeout: Duration) async throws {
        if earlyAcks.remove(clientMessageId) != nil {
            return
        }
        try await withThrowingTaskGroup(of: Void.self) { group in
            group.addTask {
                await withCheckedContinuation { cont in
                    Task {
                        await self.registerOrResolveContinuation(
                            clientMessageId: clientMessageId,
                            cont: cont
                        )
                    }
                }
            }
            group.addTask {
                try await Task.sleep(for: timeout)
                throw WebSocketError.deliveryTimeout
            }
            do {
                try await group.next()
                group.cancelAll()
            } catch {
                group.cancelAll()
                // Test boyutunda dogal akisi koru — gercek implementasyon
                // pending continuation'i temizler.
                await self.cancelContinuation(clientMessageId: clientMessageId)
                throw error
            }
        }
    }

    private func registerOrResolveContinuation(
        clientMessageId: String,
        cont: CheckedContinuation<Void, Never>
    ) {
        // Suspend sirasinda yeni bir ack daha gelmis olabilir.
        if earlyAcks.remove(clientMessageId) != nil {
            cont.resume()
            return
        }
        ackContinuations[clientMessageId] = cont
    }

    private func cancelContinuation(clientMessageId: String) {
        if let cont = ackContinuations.removeValue(forKey: clientMessageId) {
            cont.resume()
        }
    }
}

// MARK: - Tests

/// V1.x SHIP BLOCKER regression suite — iOS WebSocket heartbeat race that
/// causes `approval_response` (and similar critical client→server messages)
/// to be silently lost when the underlying TCP connection has half-died but
/// iOS hasn't detected it yet.
///
/// Live e2e (2026-05-03) showed:
/// - 07:55:53 iOS sent approval_response, `send()` returned success (TCP
///   buffer accepted bytes).
/// - 07:56:25 iOS detected heartbeat timeout (32s later).
/// - Backend received ZERO `websocket_message_received` for that envelope.
/// - 3 minutes later backend `approval_expired` fired (broker timer), claude
///   was DENIED. User-visible result: tap Allow → write tool blocked.
///
/// Fix contract (Approach A — application-layer ACK + retry):
///   1. Every critical client→server message gets a `client_message_id` (UUID).
///   2. iOS waits up to N seconds for backend `ack` envelope echoing the id.
///   3. On ack timeout, iOS forces reconnect and retries ONCE.
///   4. If second attempt also has no ack → throws `WebSocketError.deliveryFailed`
///      so UI can surface "tap Allow again" instead of silently losing the
///      decision.
@Suite("Approval Delivery Guarantee Tests (V1.x ship blocker)")
struct ApprovalDeliveryGuaranteeTests {

    // MARK: - Happy Path

    @Test("Saglikli baglantida tek seferde teslim edilmeli, retry yok")
    func deliversOnceWhenConnectionHealthy() async throws {
        let channel = MockApprovalDeliveryChannel()
        await channel.enqueue([.delivered])

        let repo = ApprovalRepositoryImpl(
            deliveryChannel: channel,
            messageRouter: WebSocketMessageRouter(),
            ackTimeout: .seconds(2)
        )

        try await repo.submitDecision(
            approvalId: "happy-1",
            decision: .approved,
            note: nil
        )

        let sendCount = await channel.sendCallCount
        let reconnects = await channel.reconnectCount
        #expect(sendCount == 1, "Saglikli ack alindi → tek send olmali")
        #expect(reconnects == 0, "Saglikli ack alindi → reconnect yapilmamali")
    }

    @Test("Her gonderim benzersiz `client_message_id` icermeli")
    func envelopeContainsClientMessageId() async throws {
        let channel = MockApprovalDeliveryChannel()
        await channel.enqueue([.delivered])

        let repo = ApprovalRepositoryImpl(
            deliveryChannel: channel,
            messageRouter: WebSocketMessageRouter(),
            ackTimeout: .seconds(2)
        )

        try await repo.submitDecision(
            approvalId: "id-1",
            decision: .approved,
            note: nil
        )

        let envelopes = await channel.sentEnvelopes
        let envelope = try #require(envelopes.first)
        let data = try #require(envelope.data(using: .utf8))
        let object = try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])
        let metadata = try #require(object["metadata"] as? [String: Any])
        let clientMessageId = metadata["client_message_id"] as? String
        #expect(clientMessageId != nil, "Critical mesajlar `client_message_id` ICERMELI")
        #expect(!(clientMessageId ?? "").isEmpty, "client_message_id bos olmamali")
    }

    // MARK: - Stale Connection Regression

    @Test("Sessiz dususte reconnect yapilmali ve ikinci denemede teslim edilmeli")
    func retriesAfterSilentDropAndReconnects() async throws {
        let channel = MockApprovalDeliveryChannel()
        // Birinci gonderim: bug yeniden uretimi — kabul edildi gibi gorundu
        // ama ack hic gelmedi (TCP yarim-olu, mesaj kabloda kayboldu).
        // Ikinci gonderim (reconnect sonrasi): saglikli teslim.
        await channel.enqueue([.silentlyDropped, .delivered])

        let repo = ApprovalRepositoryImpl(
            deliveryChannel: channel,
            messageRouter: WebSocketMessageRouter(),
            ackTimeout: .milliseconds(200)
        )

        try await repo.submitDecision(
            approvalId: "stale-1",
            decision: .approved,
            note: nil
        )

        let sendCount = await channel.sendCallCount
        let reconnects = await channel.reconnectCount
        #expect(sendCount == 2, "Birinci ack timeout → ikinci send")
        #expect(reconnects == 1, "Ack timeout → forceReconnect cagirilmali")
    }

    @Test("Iki ardisik silent-drop sonrasi loud failure firlatilmali (sessiz kayip YOK)")
    func loudlyFailsAfterDoubleSilentDrop() async throws {
        let channel = MockApprovalDeliveryChannel()
        // Hem birinci hem ikinci deneme silent drop → kullaniciya geri bildirim
        // sart. Bug'in eski davranisi: hicbir hata yok, kullanici "Allow"
        // tap'inin kayboldugunu hic bilemiyordu.
        await channel.enqueue([.silentlyDropped, .silentlyDropped])

        let repo = ApprovalRepositoryImpl(
            deliveryChannel: channel,
            messageRouter: WebSocketMessageRouter(),
            ackTimeout: .milliseconds(200)
        )

        do {
            try await repo.submitDecision(
                approvalId: "stale-2",
                decision: .approved,
                note: nil
            )
            Issue.record("Iki silent-drop sonrasi loud failure bekleniyor")
        } catch let error as WebSocketError {
            // Beklenen: deliveryFailed (UI bunu yakalayip "tap Allow again"
            // gosterebilir). deliveryTimeout da kabul — ikisi de loud.
            switch error {
            case .deliveryFailed, .deliveryTimeout:
                break
            default:
                Issue.record("Beklenmeyen WebSocketError: \(error)")
            }
        }

        let sendCount = await channel.sendCallCount
        let reconnects = await channel.reconnectCount
        #expect(sendCount == 2, "Tam olarak iki send denemesi olmali (1 retry)")
        #expect(reconnects >= 1, "Reconnect en az bir kez denenmeli")
    }

    @Test("Send firlatilan hatada da reconnect+retry yapilmali")
    func retriesAfterSendThrows() async throws {
        let channel = MockApprovalDeliveryChannel()
        // Birinci send WebSocketError.notConnected firlatti (URLSession soketi
        // dustu farketti); ikinci deneme reconnect sonrasi basarili.
        await channel.enqueue([.failure(.notConnected), .delivered])

        let repo = ApprovalRepositoryImpl(
            deliveryChannel: channel,
            messageRouter: WebSocketMessageRouter(),
            ackTimeout: .milliseconds(200)
        )

        try await repo.submitDecision(
            approvalId: "throw-1",
            decision: .approved,
            note: nil
        )

        let sendCount = await channel.sendCallCount
        let reconnects = await channel.reconnectCount
        #expect(sendCount == 2)
        #expect(reconnects == 1)
    }

    // MARK: - Idempotency / Safety

    @Test("Retry mesaji ayni `client_message_id` ile gitmeli (backend dedup icin)")
    func retryReusesClientMessageIdForIdempotency() async throws {
        let channel = MockApprovalDeliveryChannel()
        await channel.enqueue([.silentlyDropped, .delivered])

        let repo = ApprovalRepositoryImpl(
            deliveryChannel: channel,
            messageRouter: WebSocketMessageRouter(),
            ackTimeout: .milliseconds(200)
        )

        try await repo.submitDecision(
            approvalId: "idem-1",
            decision: .approved,
            note: nil
        )

        let envelopes = await channel.sentEnvelopes
        #expect(envelopes.count == 2)

        func clientMessageId(_ envelope: String) throws -> String {
            let data = try #require(envelope.data(using: .utf8))
            let object = try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])
            let metadata = try #require(object["metadata"] as? [String: Any])
            return try #require(metadata["client_message_id"] as? String)
        }

        let first = try clientMessageId(envelopes[0])
        let second = try clientMessageId(envelopes[1])
        #expect(first == second, "Retry mesaji ayni client_message_id ile gitmeli — backend dedup ve audit korelasyonu icin")
        #expect(!first.isEmpty)
    }

    @Test("Wire shape korunmali: content hala dict olmali (eski wire-shape regression)")
    func wireShapeStillDictAfterRetryRefactor() async throws {
        let channel = MockApprovalDeliveryChannel()
        await channel.enqueue([.delivered])

        let repo = ApprovalRepositoryImpl(
            deliveryChannel: channel,
            messageRouter: WebSocketMessageRouter(),
            ackTimeout: .seconds(2)
        )

        try await repo.submitDecision(
            approvalId: "wire-stable-1",
            decision: .approved,
            note: "Allow once"
        )

        let envelopes = await channel.sentEnvelopes
        let envelope = try #require(envelopes.first)
        let data = try #require(envelope.data(using: .utf8))
        let object = try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])

        #expect(object["type"] as? String == "approval_response")
        let content = try #require(object["content"] as? [String: Any])
        #expect(content["approval_id"] as? String == "wire-stable-1")
        #expect(content["decision"] as? String == "approved")
        #expect(content["note"] as? String == "Allow once")
    }
}

// MARK: - Ack Inbox Tests

/// Backend `ack` envelope yonlendiricisi.
///
/// Backend ack semasi (`shared/api-contracts/ws/ack-messages.json`):
/// ```json
/// { "type": "ack", "metadata": { "client_message_id": "<uuid>" } }
/// ```
///
/// `ApprovalDeliveryAckInbox` bu mesajlari yakalayip bekleyen
/// `awaitAck(clientMessageId:)` cagirilarini tetikler.
@Suite("Approval Delivery Ack Inbox Tests")
struct ApprovalDeliveryAckInboxTests {

    @Test("Inbox ack mesajini bekleyen continuation'i tetiklemeli")
    func inboxResolvesPendingAck() async throws {
        let inbox = ApprovalDeliveryAckInbox()

        let waiter = Task {
            try await inbox.awaitAck(clientMessageId: "ack-1", timeout: .seconds(2))
        }

        // Kucuk gecikme — waiter kayit olsun
        try await Task.sleep(for: .milliseconds(50))

        await inbox.handleAck(clientMessageId: "ack-1")

        try await waiter.value // throw etmemeli
    }

    @Test("Timeout sonrasi awaitAck WebSocketError.deliveryTimeout firlatmali")
    func inboxTimesOutWithoutAck() async {
        let inbox = ApprovalDeliveryAckInbox()

        do {
            try await inbox.awaitAck(clientMessageId: "missing-1", timeout: .milliseconds(100))
            Issue.record("Timeout bekleniyor")
        } catch let error as WebSocketError {
            #expect(error == .deliveryTimeout)
        } catch {
            Issue.record("Beklenmeyen hata tipi: \(error)")
        }
    }

    @Test("Yabanci ack id'leri bekleyen continuation'i etkilememeli")
    func unrelatedAckIgnored() async throws {
        let inbox = ApprovalDeliveryAckInbox()

        let waiter = Task {
            try await inbox.awaitAck(clientMessageId: "want-this", timeout: .milliseconds(300))
        }

        try await Task.sleep(for: .milliseconds(30))
        await inbox.handleAck(clientMessageId: "different")

        do {
            try await waiter.value
            Issue.record("Yanlis id ile resolve edildi — timeout bekleniyordu")
        } catch let error as WebSocketError {
            #expect(error == .deliveryTimeout)
        } catch {
            Issue.record("Beklenmeyen hata tipi: \(error)")
        }
    }

    /// V1.x reviewer regression #1 — timeout pathway continuation leak yapmamali.
    /// Onceki implementasyon `clearPending` icinde continuation'i resume etmeden
    /// pending'den siliyordu → "SWIFT TASK CONTINUATION MISUSE" + xcodebuild
    /// hang. Bu test 100 ardisik timeout sonrasi:
    /// - Her cagri `deliveryTimeout` firlatmali (loud failure).
    /// - `pending` map sifirlanmis olmali (leak yok).
    /// Continuation misuse runtime tarafindan otomatik fatal-error uretecegi
    /// icin testin kendisi process'i dusururdu — gecmesi de bunu kanitlar.
    @Test("Timeout continuation leak yapmamali (reviewer regression)")
    func inboxTimeoutDoesNotLeakContinuation() async {
        let inbox = ApprovalDeliveryAckInbox()
        let burstCount = 100

        await withTaskGroup(of: Void.self) { group in
            for index in 0..<burstCount {
                group.addTask {
                    do {
                        try await inbox.awaitAck(
                            clientMessageId: "leak-\(index)",
                            timeout: .milliseconds(50)
                        )
                        Issue.record("Timeout bekleniyordu (id=\(index))")
                    } catch let error as WebSocketError {
                        #expect(error == .deliveryTimeout)
                    } catch {
                        Issue.record("Beklenmeyen hata tipi: \(error)")
                    }
                }
            }
        }

        // Tum timeout Task'larin actor'a geri dondukten sonra pending'i
        // temizledigini dogrula. Kucuk bir ek bekleme — bazi timeout
        // continuation'lari awaitAck doner dondukten sonra (cleanup
        // hop'undan kaynakli) bir tick sonra map'e dokunabilir.
        try? await Task.sleep(for: .milliseconds(100))
        let pending = await inbox.pendingCount()
        #expect(pending == 0, "Tum timeout continuation'lar temizlenmis olmali (leak yok)")
    }
}
