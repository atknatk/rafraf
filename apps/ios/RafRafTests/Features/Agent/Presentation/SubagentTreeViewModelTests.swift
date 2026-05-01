import Foundation
import Testing
@testable import RafRaf

/// SubagentTreeViewModel testleri (T1.7).
/// Repository stream tuketimi, parent->child agac kurulumu ve abonelik
/// yasam dongusu kontrol edilir.
@Suite("Subagent Tree ViewModel Tests")
struct SubagentTreeViewModelTests {

    // MARK: - Helpers

    private func makeSub(
        id: String,
        parentTaskId: String? = nil,
        status: SubagentStatus = .spawned,
        spawnedAt: TimeInterval = 0,
        sessionId: String = "s1"
    ) -> Subagent {
        Subagent(
            id: id,
            sessionId: sessionId,
            parentTaskId: parentTaskId,
            name: "n-\(id)",
            description: nil,
            promptPreview: "p-\(id)",
            subagentType: nil,
            isolation: nil,
            status: status,
            summary: nil,
            totalTokens: nil,
            toolUses: nil,
            durationMs: nil,
            activity: nil,
            spawnedAt: Date(timeIntervalSince1970: spawnedAt),
            updatedAt: nil,
            completedAt: nil
        )
    }

    // MARK: - buildTree (pure function)

    @Test("buildTree bos liste icin bos sonuc dondurmeli")
    func buildTreeEmpty() {
        let tree = SubagentTreeViewModel.buildTree(from: [])
        #expect(tree.isEmpty)
    }

    @Test("buildTree dum-duz parent'siz subagent'lari kok yapar")
    func buildTreeFlat() {
        let subs = [
            makeSub(id: "a", spawnedAt: 1),
            makeSub(id: "b", spawnedAt: 2),
            makeSub(id: "c", spawnedAt: 3)
        ]
        let tree = SubagentTreeViewModel.buildTree(from: subs)
        #expect(tree.count == 3)
        #expect(tree.map(\.id) == ["a", "b", "c"])
        for node in tree {
            #expect(node.children == nil)
        }
    }

    @Test("buildTree parent->child iliskisini kurabilmeli")
    func buildTreeParentChild() {
        let subs = [
            makeSub(id: "root", spawnedAt: 1),
            makeSub(id: "child-a", parentTaskId: "root", spawnedAt: 2),
            makeSub(id: "child-b", parentTaskId: "root", spawnedAt: 3)
        ]
        let tree = SubagentTreeViewModel.buildTree(from: subs)
        #expect(tree.count == 1)
        #expect(tree[0].id == "root")
        #expect(tree[0].children?.count == 2)
        #expect(tree[0].children?.map(\.id) == ["child-a", "child-b"])
    }

    @Test("buildTree icice nested agaci dogru olusturmali")
    func buildTreeNested() {
        let subs = [
            makeSub(id: "root", spawnedAt: 1),
            makeSub(id: "mid", parentTaskId: "root", spawnedAt: 2),
            makeSub(id: "leaf", parentTaskId: "mid", spawnedAt: 3)
        ]
        let tree = SubagentTreeViewModel.buildTree(from: subs)
        #expect(tree[0].id == "root")
        #expect(tree[0].children?[0].id == "mid")
        #expect(tree[0].children?[0].children?[0].id == "leaf")
        #expect(tree[0].children?[0].children?[0].children == nil)
    }

    @Test("buildTree orphan (parent referansi mevcut listede yok) kayitlari kok kabul eder")
    func buildTreeOrphan() {
        let subs = [
            makeSub(id: "orphan", parentTaskId: "missing-parent", spawnedAt: 1)
        ]
        let tree = SubagentTreeViewModel.buildTree(from: subs)
        #expect(tree.count == 1)
        #expect(tree[0].id == "orphan")
    }

    @Test("buildTree agac dahili sirayi spawnedAt'a gore korur")
    func buildTreeOrdering() {
        let subs = [
            makeSub(id: "root", spawnedAt: 1),
            makeSub(id: "later", parentTaskId: "root", spawnedAt: 10),
            makeSub(id: "earlier", parentTaskId: "root", spawnedAt: 5)
        ]
        let tree = SubagentTreeViewModel.buildTree(from: subs)
        #expect(tree[0].children?.map(\.id) == ["earlier", "later"])
    }

    @Test("buildTree birden fazla bagimsiz kok'u korur")
    func buildTreeMultipleRoots() {
        let subs = [
            makeSub(id: "r1", spawnedAt: 1),
            makeSub(id: "r2", spawnedAt: 2),
            makeSub(id: "r1-child", parentTaskId: "r1", spawnedAt: 3)
        ]
        let tree = SubagentTreeViewModel.buildTree(from: subs)
        #expect(tree.map(\.id) == ["r1", "r2"])
        #expect(tree[0].children?.map(\.id) == ["r1-child"])
        #expect(tree[1].children == nil)
    }

    // MARK: - subscribe / setSnapshot

    @Test("setSnapshot subagents ve hasReceivedSnapshot'i gunceller")
    @MainActor
    func setSnapshotMutatesState() {
        let repo = SubagentRepositoryImpl()
        let vm = SubagentTreeViewModel(
            observeUseCase: ObserveSubagentsUseCase(repository: repo)
        )
        #expect(vm.subagents.isEmpty)
        #expect(vm.hasReceivedSnapshot == false)

        vm.setSnapshot([makeSub(id: "a")])
        #expect(vm.subagents.count == 1)
        #expect(vm.hasReceivedSnapshot == true)
    }

    @Test("subscribe ardindan repository spawn yaparsa ViewModel guncellenir")
    @MainActor
    func subscribePropagatesUpdates() async {
        let repo = SubagentRepositoryImpl()
        let vm = SubagentTreeViewModel(
            observeUseCase: ObserveSubagentsUseCase(repository: repo)
        )
        vm.subscribe(to: "sess-1")

        // wait for initial snapshot
        try? await waitFor(condition: { vm.hasReceivedSnapshot })
        #expect(vm.subagents.isEmpty)

        await repo.apply(update: .spawn(makeSub(id: "a", sessionId: "sess-1")))

        try? await waitFor(condition: { !vm.subagents.isEmpty })
        #expect(vm.subagents.count == 1)
        #expect(vm.subagents[0].id == "a")
    }

    @Test("ayni session'a tekrar subscribe idempotent")
    @MainActor
    func subscribeIdempotent() async {
        let repo = SubagentRepositoryImpl()
        let vm = SubagentTreeViewModel(
            observeUseCase: ObserveSubagentsUseCase(repository: repo)
        )
        vm.subscribe(to: "sess-1")
        vm.subscribe(to: "sess-1") // tekrar — yeni stream baslatmamali
        #expect(vm.sessionId == "sess-1")
    }

    @Test("subscribeAll modu sessionId'yi nil birakir")
    @MainActor
    func subscribeAllMode() {
        let repo = SubagentRepositoryImpl()
        let vm = SubagentTreeViewModel(
            observeUseCase: ObserveSubagentsUseCase(repository: repo)
        )
        vm.subscribeAll()
        #expect(vm.sessionId == nil)
        #expect(vm.subscriptionMode == .all)
    }

    @Test("unsubscribe state'i temizler")
    @MainActor
    func unsubscribeClearsState() {
        let repo = SubagentRepositoryImpl()
        let vm = SubagentTreeViewModel(
            observeUseCase: ObserveSubagentsUseCase(repository: repo)
        )
        vm.subscribe(to: "sess-1")
        vm.unsubscribe()
        #expect(vm.sessionId == nil)
        #expect(vm.subscriptionMode == .none)
    }

    // MARK: - Helpers

    /// Polling helper — small intervals; gives async stream time to deliver.
    @MainActor
    private func waitFor(
        timeoutSeconds: Double = 2.0,
        condition: @MainActor () -> Bool
    ) async throws {
        let start = Date()
        while !condition() {
            if Date().timeIntervalSince(start) > timeoutSeconds {
                throw TestTimeoutError()
            }
            try? await Task.sleep(nanoseconds: 20_000_000) // 20ms
        }
    }
}

private struct TestTimeoutError: Error {}
