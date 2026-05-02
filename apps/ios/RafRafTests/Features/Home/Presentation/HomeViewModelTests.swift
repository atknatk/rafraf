import Foundation
import Testing
@testable import RafRaf

/// HomeViewModel testleri.
@Suite("HomeViewModel Tests")
struct HomeViewModelTests {

    // MARK: - Helpers

    /// Test stub: SessionTitleRepositoryProtocol.
    private actor StubSessionTitleRepository: SessionTitleRepositoryProtocol {
        private var continuations: [UUID: AsyncStream<SessionTitleUpdate>.Continuation] = [:]
        private var cache: [String: SessionTitleUpdate] = [:]

        nonisolated func titleUpdates() -> AsyncStream<SessionTitleUpdate> {
            AsyncStream { continuation in
                let token = UUID()
                Task { [weak self] in
                    await self?.subscribe(token: token, continuation: continuation)
                }
                continuation.onTermination = { [weak self] _ in
                    Task { [weak self] in
                        await self?.unsubscribe(token: token)
                    }
                }
            }
        }

        func snapshot() async -> [String: SessionTitleUpdate] { cache }

        func emit(_ update: SessionTitleUpdate) {
            cache[update.sessionId] = update
            for continuation in continuations.values {
                continuation.yield(update)
            }
        }

        private func subscribe(
            token: UUID,
            continuation: AsyncStream<SessionTitleUpdate>.Continuation
        ) {
            continuations[token] = continuation
            for update in cache.values {
                continuation.yield(update)
            }
        }

        private func unsubscribe(token: UUID) {
            continuations.removeValue(forKey: token)
        }
    }

    // MARK: - Initial state

    @Test("HomeViewModel baslangic durumu dogru olmali")
    @MainActor
    func initialState() {
        let viewModel = HomeViewModel()

        #expect(viewModel.isLoading == false)
        #expect(viewModel.errorMessage == nil)
        #expect(viewModel.sessions.isEmpty)
    }

    @Test("loadData isLoading durumunu degistirmeli")
    @MainActor
    func loadDataUpdatesLoading() async {
        let viewModel = HomeViewModel()

        await viewModel.loadData()

        // loadData tamamlandiktan sonra isLoading false olmali
        #expect(viewModel.isLoading == false)
    }

    // MARK: - Session seeding

    @Test("seedSessions liste icerigini yerlestirmeli")
    @MainActor
    func seedSessionsPopulatesList() {
        let viewModel = HomeViewModel()
        let session = HomeSession(id: "s1", title: "raw")
        viewModel.seedSessions([session])

        #expect(viewModel.sessions.count == 1)
        #expect(viewModel.sessions[0].id == "s1")
        #expect(viewModel.sessions[0].displayTitle == "raw")
    }

    // MARK: - applyTitleUpdate

    @Test("applyTitleUpdate eslesen sessionun aiTitle alanini guncellemeli")
    @MainActor
    func applyTitleUpdateUpdatesMatchingSession() {
        let viewModel = HomeViewModel()
        viewModel.seedSessions([
            HomeSession(id: "s1", title: "raw 1"),
            HomeSession(id: "s2", title: "raw 2")
        ])

        viewModel.applyTitleUpdate(
            SessionTitleUpdate(sessionId: "s2", aiTitle: "AI baslik 2", generatedAt: Date())
        )

        #expect(viewModel.sessions[0].aiTitle == nil)
        #expect(viewModel.sessions[1].aiTitle == "AI baslik 2")
        #expect(viewModel.sessions[1].displayTitle == "AI baslik 2")
        #expect(viewModel.sessions[1].hasAITitle)
    }

    @Test("applyTitleUpdate listede yoksa hicbir sessionu degistirmemeli")
    @MainActor
    func applyTitleUpdateIgnoresUnknownSession() {
        let viewModel = HomeViewModel()
        viewModel.seedSessions([HomeSession(id: "s1", title: "raw 1")])

        viewModel.applyTitleUpdate(
            SessionTitleUpdate(sessionId: "missing", aiTitle: "x", generatedAt: Date())
        )

        #expect(viewModel.sessions[0].aiTitle == nil)
        #expect(viewModel.sessions[0].displayTitle == "raw 1")
    }

    // MARK: - Stream observation

    @Test("loadData repository emit ettiginde sessionun baslii canli guncellenmeli")
    @MainActor
    func observesRepositoryStream() async throws {
        let repository = StubSessionTitleRepository()
        let useCase = ObserveSessionTitleUpdatesUseCase(repository: repository)
        let viewModel = HomeViewModel(observeSessionTitleUpdatesUseCase: useCase)
        viewModel.seedSessions([HomeSession(id: "s1", title: "raw")])

        await viewModel.loadData()

        // Repository emit eder
        await repository.emit(
            SessionTitleUpdate(sessionId: "s1", aiTitle: "yeni baslik", generatedAt: Date())
        )

        // AsyncStream propagation icin kisa bir bekleyis gerekiyor
        try await waitForCondition(timeout: 1.0) { @MainActor in
            viewModel.sessions.first?.aiTitle == "yeni baslik"
        }

        #expect(viewModel.sessions[0].aiTitle == "yeni baslik")
        #expect(viewModel.sessions[0].displayTitle == "yeni baslik")
    }

    @Test("loadData repository snapshot'unu replay etmeli")
    @MainActor
    func replaysSnapshotOnLoad() async {
        let repository = StubSessionTitleRepository()
        await repository.emit(
            SessionTitleUpdate(sessionId: "s1", aiTitle: "cached", generatedAt: Date())
        )
        let useCase = ObserveSessionTitleUpdatesUseCase(repository: repository)
        let viewModel = HomeViewModel(observeSessionTitleUpdatesUseCase: useCase)
        viewModel.seedSessions([HomeSession(id: "s1", title: "raw")])

        await viewModel.loadData()

        #expect(viewModel.sessions[0].aiTitle == "cached")
    }

    // MARK: - Helpers

    private func waitForCondition(
        timeout: TimeInterval,
        condition: @MainActor () -> Bool
    ) async throws {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if await MainActor.run(body: condition) { return }
            try await Task.sleep(nanoseconds: 20_000_000)
        }
        throw NSError(domain: "TestTimeout", code: 1)
    }
}
