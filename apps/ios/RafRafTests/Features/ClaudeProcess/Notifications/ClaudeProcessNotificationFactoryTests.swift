import Foundation
import os
import Testing
@preconcurrency import UserNotifications
@testable import RafRaf

/// V1.x SLIM (Item 11) — Lokal bildirim factory testleri.
///
/// `UNUserNotificationCenter`'a karsi kosulmasi mumkun olmadigindan
/// `UNNotificationCenterScheduling` protokolune mock ekledik; factory mock
/// merkez ile insantiate edilir, request'lerin gectigi dogrulanir.
@Suite("ClaudeProcessNotificationFactory tests")
struct ClaudeProcessNotificationFactoryTests {

    /// Lock-protected mutable state — `UNNotificationRequest` Apple
    /// tarafindan henuz `Sendable` deklare edilmedi, bu yuzden actor isolation
    /// yerine `OSAllocatedUnfairLock` (async-safe) ile sariliyoruz.
    private final class MockCenter: UNNotificationCenterScheduling, @unchecked Sendable {
        private let storage = OSAllocatedUnfairLock<[UNNotificationRequest]>(initialState: [])
        private let shouldFail: Bool

        init(shouldFail: Bool = false) {
            self.shouldFail = shouldFail
        }

        func add(_ request: UNNotificationRequest) async throws {
            if shouldFail {
                throw NSError(domain: "MockCenter", code: 1)
            }
            storage.withLock { $0.append(request) }
        }

        func snapshot() -> [UNNotificationRequest] {
            storage.withLock { $0 }
        }
    }

    @Test("Stalled bildirim center'a iletilir")
    func stalledNotificationFires() async {
        let center = MockCenter()
        let factory = ClaudeProcessNotificationFactory(center: center)
        await factory.fire(
            sessionId: "abcdef-1234",
            kind: .stalled,
            detail: "tail"
        )
        let requests = center.snapshot()
        #expect(requests.count == 1)
        #expect(requests[0].identifier == "claude.process.stalled.abcdef-1234")
    }

    @Test("Crashed bildirim title + body doldurulur")
    func crashedNotificationHasContent() async {
        let center = MockCenter()
        let factory = ClaudeProcessNotificationFactory(center: center)
        await factory.fire(
            sessionId: "deadbeef",
            kind: .crashed,
            detail: "exit code 137"
        )
        let requests = center.snapshot()
        #expect(requests.count == 1)
        let content = requests[0].content
        #expect(!content.title.isEmpty)
        #expect(!content.body.isEmpty)
    }

    @Test("Ayni session+kind ikinci kez tetiklendiginde yeni request OS coalesce eder")
    func dedupePerSession() async {
        let center = MockCenter()
        let factory = ClaudeProcessNotificationFactory(center: center)
        await factory.fire(sessionId: "s1", kind: .stalled, detail: nil)
        await factory.fire(sessionId: "s1", kind: .stalled, detail: nil)
        let requests = center.snapshot()
        // Mock 2 entry kaydeder — gercek `UNUserNotificationCenter` ayni
        // identifier'i replace eder. Burada sadece identifier'larin ayni
        // oldugunu dogrularz.
        #expect(requests.count == 2)
        #expect(requests[0].identifier == requests[1].identifier)
    }

    @Test("Center add hatasi yutulur (no throw)")
    func failingCenterDoesNotThrow() async {
        let center = MockCenter(shouldFail: true)
        let factory = ClaudeProcessNotificationFactory(center: center)
        // Hata firlatmamali — factory icinde catch'lenir
        await factory.fire(sessionId: "s1", kind: .rateLimited, detail: nil)
        let requests = center.snapshot()
        #expect(requests.isEmpty)
    }
}
