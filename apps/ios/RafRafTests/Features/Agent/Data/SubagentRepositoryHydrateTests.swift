import Foundation
import Testing
@testable import RafRaf

/// Item 9 — `SubagentRepository.hydrate(sessionId:)` REST hydration testleri.
///
/// `URLProtocol`-based stubbing ile NetworkClient'in `URLSession` katmaninı
/// mocklariz. Production NetworkClient implementasyonu degismeden test
/// edilebilir: sadece istegimizin path'i + mock response'umuz dogru olsun.
@Suite("Subagent Repository Hydrate Tests")
struct SubagentRepositoryHydrateTests {

    // MARK: - Helpers

    /// Test-isolated NetworkClient olusturur — istek `MockHydrateURLProtocol`
    /// uzerinden gider; configure helper ile per-test response saglanir.
    private func makeNetworkClient() -> NetworkClient {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [MockHydrateURLProtocol.self]
        let session = URLSession(configuration: config)
        return NetworkClient(
            baseURL: URL(string: "https://test.local/api/v1")!,
            session: session
        )
    }

    private func sampleDTOJSON(sessionId: String) -> String {
        """
        [
          {
            "id": "task-rest-1",
            "parent_id": null,
            "session_id": "\(sessionId)",
            "status": "in_progress",
            "name": "developer",
            "description": "implement feature",
            "prompt_preview": "build the new pill",
            "subagent_type": "developer",
            "isolation": "worktree",
            "summary": null,
            "total_tokens": null,
            "tool_uses": null,
            "duration_ms": null,
            "activity": "writing tests",
            "started_at": "2026-05-03T10:00:00.000Z",
            "completed_at": null,
            "updated_at": "2026-05-03T10:01:00.000Z",
            "progress_percent": 42.0
          }
        ]
        """
    }

    // MARK: - No network client = no-op

    @Test("hydrate: networkClient nil ise sessizce no-op")
    func hydrate_noNetworkClient_isNoop() async throws {
        let repo = SubagentRepositoryImpl(networkClient: nil)
        // Hata firlatmamali, state'e dokunmamali
        try await repo.hydrate(sessionId: "any")
        let snapshot = await repo.currentSubagents(sessionId: "any")
        #expect(snapshot.isEmpty)
    }

    // MARK: - Successful hydrate

    @Test("hydrate: backend snapshot in-memory store'a merge edilmeli")
    func hydrate_success_mergesIntoStore() async throws {
        let sessionId = "session-hydrate-1"
        MockHydrateURLProtocol.set(
            response: .success(body: Data(sampleDTOJSON(sessionId: sessionId).utf8)),
            forPathSuffix: "/sessions/\(sessionId)/subagents"
        )

        let repo = SubagentRepositoryImpl(networkClient: makeNetworkClient())
        try await repo.hydrate(sessionId: sessionId)

        let snapshot = await repo.currentSubagents(sessionId: sessionId)
        #expect(snapshot.count == 1)
        #expect(snapshot[0].id == "task-rest-1")
        #expect(snapshot[0].name == "developer")
        #expect(snapshot[0].status == .inProgress)
        #expect(snapshot[0].activity == "writing tests")
        #expect(snapshot[0].isolation == "worktree")
    }

    // MARK: - Idempotency: existing in-memory entry wins

    @Test("hydrate: ayni id icin in-memory entry korunur (server overwrite YOK)")
    func hydrate_idempotent_existingWins() async throws {
        let sessionId = "session-hydrate-2"
        MockHydrateURLProtocol.set(
            response: .success(body: Data(sampleDTOJSON(sessionId: sessionId).utf8)),
            forPathSuffix: "/sessions/\(sessionId)/subagents"
        )

        let repo = SubagentRepositoryImpl(networkClient: makeNetworkClient())
        // Once in-memory state'i WS push gibi besle (farkli activity ile)
        let existing = Subagent(
            id: "task-rest-1",
            sessionId: sessionId,
            parentTaskId: nil,
            name: "developer-local",
            description: nil,
            promptPreview: "ws push only",
            subagentType: "developer",
            isolation: nil,
            status: .completed,
            summary: "ws sentinel",
            totalTokens: 999,
            toolUses: 5,
            durationMs: 12345,
            activity: "ws activity",
            spawnedAt: Date(timeIntervalSince1970: 1_700_000_000),
            updatedAt: Date(timeIntervalSince1970: 1_700_000_500),
            completedAt: Date(timeIntervalSince1970: 1_700_000_500)
        )
        await repo.apply(update: .spawn(existing))

        try await repo.hydrate(sessionId: sessionId)

        let snapshot = await repo.currentSubagents(sessionId: sessionId)
        #expect(snapshot.count == 1)
        // In-memory entry KORUNMALI
        #expect(snapshot[0].name == "developer-local")
        #expect(snapshot[0].activity == "ws activity")
        #expect(snapshot[0].status == .completed)
        #expect(snapshot[0].summary == "ws sentinel")
    }

    // MARK: - Error path

    @Test("hydrate: backend 404 verirse hata firlatir, in-memory state korunur")
    func hydrate_serverError_throwsKeepsState() async throws {
        let sessionId = "session-hydrate-3"
        MockHydrateURLProtocol.set(
            response: .httpError(statusCode: 404),
            forPathSuffix: "/sessions/\(sessionId)/subagents"
        )

        let repo = SubagentRepositoryImpl(networkClient: makeNetworkClient())
        // In-memory'ye bir entry koy
        let local = Subagent(
            id: "local-only",
            sessionId: sessionId,
            parentTaskId: nil,
            name: "local",
            description: nil,
            promptPreview: "local",
            subagentType: nil,
            isolation: nil,
            status: .inProgress,
            summary: nil,
            totalTokens: nil,
            toolUses: nil,
            durationMs: nil,
            activity: nil,
            spawnedAt: Date(timeIntervalSince1970: 1_700_000_000),
            updatedAt: nil,
            completedAt: nil
        )
        await repo.apply(update: .spawn(local))

        var didThrow = false
        do {
            try await repo.hydrate(sessionId: sessionId)
        } catch {
            didThrow = true
        }
        #expect(didThrow == true)
        // In-memory state korunmali
        let snapshot = await repo.currentSubagents(sessionId: sessionId)
        #expect(snapshot.count == 1)
        #expect(snapshot[0].id == "local-only")
    }
}

// MARK: - URLProtocol mock

/// Per-test response state'ini paylasan URLProtocol stub.
/// Senkron tasarim — Task spawn etmeden response donecek; URLSession bunu
/// kendi internal queue'sunda calistirir, dolayisi ile ek concurrency yok.
/// State paylasimi: NSLock korumali static dictionary.
final class MockHydrateURLProtocol: URLProtocol, @unchecked Sendable {
    enum StubResponse: @unchecked Sendable {
        case success(body: Data)
        case httpError(statusCode: Int)
    }

    private static let lock = NSLock()
    nonisolated(unsafe) private static var responses: [String: StubResponse] = [:]

    static func set(response: StubResponse, forPathSuffix suffix: String) {
        lock.lock()
        defer { lock.unlock() }
        responses[suffix] = response
    }

    static func reset() {
        lock.lock()
        defer { lock.unlock() }
        responses.removeAll()
    }

    private static func lookup(for path: String) -> StubResponse? {
        lock.lock()
        defer { lock.unlock() }
        for (suffix, response) in responses where path.hasSuffix(suffix) {
            return response
        }
        return nil
    }

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        let path = request.url?.path ?? ""
        let response = Self.lookup(for: path)
        switch response {
        case .success(let body):
            let httpResponse = HTTPURLResponse(
                url: request.url ?? URL(string: "https://test.local")!,
                statusCode: 200,
                httpVersion: "HTTP/1.1",
                headerFields: ["Content-Type": "application/json"]
            )!
            client?.urlProtocol(self, didReceive: httpResponse, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: body)
            client?.urlProtocolDidFinishLoading(self)
        case .httpError(let statusCode):
            let httpResponse = HTTPURLResponse(
                url: request.url ?? URL(string: "https://test.local")!,
                statusCode: statusCode,
                httpVersion: "HTTP/1.1",
                headerFields: nil
            )!
            client?.urlProtocol(self, didReceive: httpResponse, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: Data())
            client?.urlProtocolDidFinishLoading(self)
        case .none:
            client?.urlProtocol(self, didFailWithError: URLError(.fileDoesNotExist))
        }
    }

    override func stopLoading() {}
}
