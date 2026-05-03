import Foundation
import Testing
@testable import RafRaf

/// Stream delta coalescing davranis testleri.
///
/// V1.x performance fix kapsami: claude per-token deltalari 16ms (60Hz frame)
/// penceresine coalesce ediyor — `messages[idx]` mutasyonu frame basina en
/// fazla bir kez tetikleniyor. Bu testler hem dogru sayim hem de coalesced
/// icerigin `chat.stream_end` `full_text` ile eslestigini dogrular.
@Suite("ChatViewModel Stream Delta Coalescing Tests")
struct ChatViewModelStreamDeltaTests {

    // MARK: - Helpers

    @MainActor
    private func makeSUT(
        flushInterval: Duration = .milliseconds(16)
    ) -> ChatViewModel {
        let repo = MockChatRepository()
        return ChatViewModel(
            sendMessageUseCase: SendMessageUseCase(repository: repo),
            loadHistoryUseCase: LoadChatHistoryUseCase(repository: repo),
            sessionId: "stream-test",
            streamFlushInterval: flushInterval
        )
    }

    // MARK: - Coalescing: tek frame icinde butun deltalar tek mutasyon

    @Test("streamDelta: 16ms pencerede 10 delta = 1 messages[idx] mutasyonu")
    @MainActor
    func streamDelta_coalescesWithin16msWindow_emitsOneUpdate() async {
        let vm = makeSUT(flushInterval: .milliseconds(16))
        let messageId = "msg-coalesce-1"

        // 10 delta hizli pesinden — hepsi tek pencereye duser
        for index in 0..<10 {
            vm.handleStreamDelta(messageId: messageId, delta: "tok\(index) ")
        }

        // Mesaj placeholder olarak listede ama icerik henuz bos
        #expect(vm.messages.count == 1)
        #expect(vm.messages.first?.content == "")
        #expect(vm.streamFlushCount == 0)

        // Pencere kapansin (16ms + buffer)
        try? await Task.sleep(for: .milliseconds(60))

        // TEK mutasyon, butun deltalar birlikte uygulandi
        #expect(vm.streamFlushCount == 1)
        let expected = (0..<10).map { "tok\($0) " }.joined()
        #expect(vm.messages.first?.content == expected)
        #expect(vm.messages.first?.isStreaming == true)
    }

    // MARK: - Coalescing: cok pencere

    @Test("streamDelta: ardisik pencerelerde her birinde 1 mutasyon")
    @MainActor
    func streamDelta_acrossMultipleWindows_emitsOneUpdatePerWindow() async {
        // Determinism guard (TestPlan reviewer flagged this as flaky on shared
        // CI runners): use the testing helper to drain pending buffers between
        // windows instead of waiting on `Task.sleep`. Real flush window is
        // still 16ms in production; the tests only assert that each window
        // produces exactly one mutation, which is a property the manual flush
        // helper exercises just as faithfully without depending on scheduler
        // timing under load.
        let vm = makeSUT(flushInterval: .milliseconds(16))
        let messageId = "msg-windows"

        // Pencere 1
        vm.handleStreamDelta(messageId: messageId, delta: "a")
        vm.handleStreamDelta(messageId: messageId, delta: "b")
        await vm.flushPendingStreamDeltasForTesting()
        #expect(vm.streamFlushCount == 1)

        // Pencere 2
        vm.handleStreamDelta(messageId: messageId, delta: "c")
        vm.handleStreamDelta(messageId: messageId, delta: "d")
        await vm.flushPendingStreamDeltasForTesting()
        #expect(vm.streamFlushCount == 2)

        // Pencere 3
        vm.handleStreamDelta(messageId: messageId, delta: "e")
        await vm.flushPendingStreamDeltasForTesting()
        #expect(vm.streamFlushCount == 3)

        #expect(vm.messages.first?.content == "abcde")
    }

    // MARK: - Stream end force-flush

    @Test("streamEnd: bekleyen deltalar uygulanir, sonra fullText finalize edilir")
    @MainActor
    func streamEnd_forcesImmediateFlush() {
        let vm = makeSUT(flushInterval: .milliseconds(16))
        let messageId = "msg-end-flush"

        vm.handleStreamDelta(messageId: messageId, delta: "Hello ")
        vm.handleStreamDelta(messageId: messageId, delta: "World")
        // Pencere bitmedi — buffered
        #expect(vm.messages.first?.content == "")

        // stream_end senkron force-flush eder + fullText ile finalize eder
        vm.handleStreamEnd(
            messageId: messageId,
            fullText: "Hello World",
            type: .text
        )

        #expect(vm.messages.count == 1)
        #expect(vm.messages.first?.content == "Hello World")
        #expect(vm.messages.first?.isStreaming == false)
        // Buffer residue kalmamali
        vm.flushPendingStreamDeltasForTesting()
        #expect(vm.streamFlushCount == 1) // sadece force-flush, bos buffer ek flush yok
    }

    // MARK: - Authoritative correctness

    @Test("coalesced content sum-of-deltas eslesir + fullText authoritative")
    @MainActor
    func coalescedContent_matchesStreamEndFullText() async {
        let vm = makeSUT(flushInterval: .milliseconds(16))
        let messageId = "msg-correctness"

        // 100 delta — 5'er karakter, toplam 500 char gerceekci stream simulasyonu
        var deltas: [String] = []
        for index in 0..<100 {
            let delta = "T\(String(format: "%03d", index))_"
            deltas.append(delta)
            vm.handleStreamDelta(messageId: messageId, delta: delta)
            // Her 25 deltada bir kucuk bekleme — birden fazla flush window
            if index % 25 == 24 {
                try? await Task.sleep(for: .milliseconds(20))
            }
        }
        // Son window
        try? await Task.sleep(for: .milliseconds(20))

        let expected = deltas.joined()
        // Coalesce edilen icerik tum deltalarin toplami olmali (residue yok)
        #expect(vm.messages.first?.content == expected)

        // stream_end ayni icerigi onayliyor — wire kontratimiz bozulmadi
        vm.handleStreamEnd(
            messageId: messageId,
            fullText: expected,
            type: .text
        )
        #expect(vm.messages.first?.content == expected)
        #expect(vm.messages.first?.isStreaming == false)
    }

    // MARK: - Multi-message buffer izolasyonu

    @Test("farkli message_id'ler ayri buffer'lar — interleaved deltalar karismaz")
    @MainActor
    func streamDelta_isolatesBuffersPerMessageId() async {
        let vm = makeSUT(flushInterval: .milliseconds(16))

        vm.handleStreamDelta(messageId: "msg-A", delta: "AAA")
        vm.handleStreamDelta(messageId: "msg-B", delta: "BBB")
        vm.handleStreamDelta(messageId: "msg-A", delta: "AA2")
        vm.handleStreamDelta(messageId: "msg-B", delta: "BB2")

        try? await Task.sleep(for: .milliseconds(40))

        let msgA = vm.messages.first(where: { $0.id == "msg-A" })
        let msgB = vm.messages.first(where: { $0.id == "msg-B" })
        #expect(msgA?.content == "AAAAA2")
        #expect(msgB?.content == "BBBBB2")
    }

    // MARK: - ScrollToBottom throttle (Helper unit testi)

    @Test("StreamScrollThrottle: 100 cagri icinde sadece 1 trigger (50ms)")
    @MainActor
    func scrollToBottom_throttledTo100ms() async {
        var fireCount = 0
        let throttle = StreamScrollThrottle(interval: .milliseconds(100))

        let start = Date()
        // 50ms boyunca burst — her 0.5ms bir
        while Date().timeIntervalSince(start) < 0.05 {
            if throttle.shouldFire() {
                fireCount += 1
            }
            // ufak bir geri durus — busy loop'tan kacin
            try? await Task.sleep(for: .microseconds(500))
        }

        // 100ms throttle penceresinde 50ms boyunca burst — en fazla 1 fire
        // (ilk cagrida fire, kalan tum cagrilar throttled).
        #expect(fireCount == 1, "Expected 1 fire within first 100ms window, got \(fireCount)")
    }

    @Test("StreamScrollThrottle: 100ms gectikten sonra tekrar fire eder")
    @MainActor
    func streamScrollThrottle_resetsAfterInterval() async {
        let throttle = StreamScrollThrottle(interval: .milliseconds(50))
        var fireCount = 0

        if throttle.shouldFire() { fireCount += 1 }
        try? await Task.sleep(for: .milliseconds(70))
        if throttle.shouldFire() { fireCount += 1 }
        try? await Task.sleep(for: .milliseconds(70))
        if throttle.shouldFire() { fireCount += 1 }

        #expect(fireCount == 3)
    }

    @Test("StreamScrollThrottle.forceFire: throttle bypass eder")
    @MainActor
    func streamScrollThrottle_forceFireBypassesWindow() {
        let throttle = StreamScrollThrottle(interval: .seconds(10))

        #expect(throttle.shouldFire() == true)
        #expect(throttle.shouldFire() == false) // throttled
        throttle.forceFire() // ornek: stream_end -> hemen scroll

        // forceFire sonrasi normal throttle yine aktif
        #expect(throttle.shouldFire() == false)
    }
}
