import Foundation
import Testing
@testable import RafRaf

/// `SessionTitleRepositoryImpl` testleri.
@Suite("SessionTitleRepositoryImpl Tests")
struct SessionTitleRepositoryImplTests {

    @Test("handle(content:) gelen DTO'yu domain modeline cevirip emit etmeli")
    func handleContentEmitsDomainUpdate() async throws {
        let repository = SessionTitleRepositoryImpl()
        let stream = repository.titleUpdates()

        let date = Date(timeIntervalSince1970: 1_714_500_000)
        let uuid = UUID(uuidString: "22222222-2222-2222-2222-222222222222")!
        let content = SessionTitleContent(
            sessionId: uuid,
            aiTitle: "Yeni baslik",
            generatedAt: date
        )

        // Subscribe Task baslayabilsin diye minik bir bekleme
        try await Task.sleep(nanoseconds: 50_000_000)
        await repository.handle(content: content)

        let received = await firstUpdate(from: stream, timeout: 1.0)

        #expect(received != nil)
        #expect(received?.sessionId == uuid.uuidString.lowercased())
        #expect(received?.aiTitle == "Yeni baslik")
        #expect(received?.generatedAt == date)
    }

    @Test("snapshot() en son guncellemeleri sessionId anahtarinda saklamali")
    func snapshotStoresLatestUpdate() async {
        let repository = SessionTitleRepositoryImpl()

        await repository.emit(
            SessionTitleUpdate(sessionId: "s1", aiTitle: "v1", generatedAt: Date())
        )
        await repository.emit(
            SessionTitleUpdate(sessionId: "s1", aiTitle: "v2", generatedAt: Date())
        )
        await repository.emit(
            SessionTitleUpdate(sessionId: "s2", aiTitle: "x", generatedAt: Date())
        )

        let snapshot = await repository.snapshot()

        #expect(snapshot.count == 2)
        #expect(snapshot["s1"]?.aiTitle == "v2")
        #expect(snapshot["s2"]?.aiTitle == "x")
    }

    @Test("Yeni abone snapshot'u replay olarak almali")
    func newSubscriberReplaysSnapshot() async throws {
        let repository = SessionTitleRepositoryImpl()
        await repository.emit(
            SessionTitleUpdate(sessionId: "s1", aiTitle: "cached", generatedAt: Date())
        )

        let stream = repository.titleUpdates()
        let replayed = await firstUpdate(from: stream, timeout: 1.0)

        #expect(replayed?.sessionId == "s1")
        #expect(replayed?.aiTitle == "cached")
    }

    @Test("Birden fazla abone ayni event'i almali (broadcast)")
    func broadcastsToMultipleSubscribers() async throws {
        let repository = SessionTitleRepositoryImpl()
        let stream1 = repository.titleUpdates()
        let stream2 = repository.titleUpdates()

        try await Task.sleep(nanoseconds: 50_000_000)
        await repository.emit(
            SessionTitleUpdate(sessionId: "s1", aiTitle: "broadcast", generatedAt: Date())
        )

        async let r1Task = firstUpdate(from: stream1, timeout: 1.0)
        async let r2Task = firstUpdate(from: stream2, timeout: 1.0)
        let r1 = await r1Task
        let r2 = await r2Task

        #expect(r1?.aiTitle == "broadcast")
        #expect(r2?.aiTitle == "broadcast")
    }

    // MARK: - Helpers

    /// AsyncStream'den ilk degeri (varsa) timeout suresi icinde alir.
    /// Iterator non-Sendable oldugu icin tek Task icinde tutulur.
    private func firstUpdate(
        from stream: AsyncStream<SessionTitleUpdate>,
        timeout: TimeInterval
    ) async -> SessionTitleUpdate? {
        await withTaskGroup(of: SessionTitleUpdate?.self) { group in
            group.addTask {
                for await update in stream {
                    return update
                }
                return nil
            }
            group.addTask {
                try? await Task.sleep(nanoseconds: UInt64(timeout * 1_000_000_000))
                return nil
            }
            let value = await group.next() ?? nil
            group.cancelAll()
            return value
        }
    }
}
