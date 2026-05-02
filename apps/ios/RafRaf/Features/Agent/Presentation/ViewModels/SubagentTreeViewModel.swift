import Foundation

/// Bir Subagent agacinin tek dugumu — OutlineGroup tarafindan tuketilir.
///
/// `Subagent.parentTaskId` degeri varsa o subagent baska bir subagent'in
/// alt dugumu olur; yoksa kok dugumdur. `children` `nil` olursa OutlineGroup
/// satiri terminal kabul eder; bos liste `[]` ise expandable ama bos kabul
/// edilir. Bu yuzden cocuksuz kayitlarda `nil` doneriz.
struct SubagentNode: Identifiable, Sendable, Hashable {
    let subagent: Subagent
    let children: [SubagentNode]?

    var id: String { subagent.id }
}

/// SubagentTreeView'in state'ini yoneten ViewModel.
///
/// Repository'den AsyncStream tuketir, `subagents` array'ini gunceller,
/// tree compute property tarafindan turetilir. ContentView seviyesinde
/// session ID alinir; her session degisiminde yeni stream baslatilir
/// (`subscribe(to:)`).
@MainActor
@Observable
final class SubagentTreeViewModel {
    /// Aktif session icin tum subagent'lar — `spawnedAt` artan sirada.
    private(set) var subagents: [Subagent] = []

    /// Stream subscribe olduktan sonra ilk snapshot dustugunde true olur.
    /// UI bu degeri kullanarak loading placeholder'i gizler.
    private(set) var hasReceivedSnapshot = false

    /// Hangi modda abone olundugu (belirli session veya tum oturumlar).
    private(set) var subscriptionMode: SubscriptionMode = .none

    /// Aktif sessionId — `subscriptionMode == .session` ise dolu olur.
    var sessionId: String? {
        if case .session(let id) = subscriptionMode { return id }
        return nil
    }

    private let observeUseCase: ObserveSubagentsUseCase
    private var streamTask: Task<Void, Never>?

    init(observeUseCase: ObserveSubagentsUseCase) {
        self.observeUseCase = observeUseCase
    }

    // NOTE: stream task lifecycle: View'in `.onDisappear` callback'inde
    // `unsubscribe()` cagrilir. ViewModel'in deinit'inde @MainActor isolation
    // ile uyumsuz oldugu icin manuel cleanup gerekmez (Task otomatik cancel
    // olur subscriber yok oldugunda — AsyncStream onTermination tetiklenir).

    /// Belirtilen session icin stream'i baslatir. Eger ayni session zaten
    /// abone ise idempotent — yeniden subscribe etmez.
    func subscribe(to sessionId: String) {
        if case .session(let current) = subscriptionMode,
           current == sessionId,
           streamTask != nil {
            return
        }
        unsubscribe()
        self.subscriptionMode = .session(sessionId)
        self.hasReceivedSnapshot = false
        self.subagents = []

        streamTask = Task { [weak self, observeUseCase] in
            let stream = await observeUseCase.execute(sessionId: sessionId)
            for await snapshot in stream {
                guard !Task.isCancelled else { return }
                await MainActor.run {
                    guard let self else { return }
                    self.subagents = snapshot
                    self.hasReceivedSnapshot = true
                }
            }
        }
    }

    /// Tum oturumlardaki subagent'lari toplu olarak izle.
    func subscribeAll() {
        if case .all = subscriptionMode, streamTask != nil { return }
        unsubscribe()
        self.subscriptionMode = .all
        self.hasReceivedSnapshot = false
        self.subagents = []

        streamTask = Task { [weak self, observeUseCase] in
            let stream = await observeUseCase.executeAll()
            for await snapshot in stream {
                guard !Task.isCancelled else { return }
                await MainActor.run {
                    guard let self else { return }
                    self.subagents = snapshot
                    self.hasReceivedSnapshot = true
                }
            }
        }
    }

    /// Aktif stream'i iptal eder. View kapandigi zaman cagrilir.
    func unsubscribe() {
        streamTask?.cancel()
        streamTask = nil
        subscriptionMode = .none
    }

    /// Stream abonelik modu.
    enum SubscriptionMode: Equatable, Sendable {
        case none
        case session(String)
        case all
    }

    /// Test / preview icin manuel snapshot atamasi yapar.
    func setSnapshot(_ subagents: [Subagent]) {
        self.subagents = subagents
        self.hasReceivedSnapshot = true
    }

    /// `subagents` array'inden parent->child agaci insa eder.
    /// Root = `parentTaskId == nil` veya parent referansi mevcut listede
    /// bulunamayan subagent'lar (orphan korumasi).
    var tree: [SubagentNode] {
        Self.buildTree(from: subagents)
    }

    /// Pure / saf agac insa fonksiyonu — test edilebilir olmasi icin static
    /// ve `nonisolated`. Sadece input array'ine bakar; ViewModel state'ini
    /// degistirmedigi icin actor isolation gerektirmez.
    nonisolated static func buildTree(from subagents: [Subagent]) -> [SubagentNode] {
        guard !subagents.isEmpty else { return [] }
        let allIds = Set(subagents.map(\.id))
        var childrenByParent: [String: [Subagent]] = [:]
        var roots: [Subagent] = []
        for sub in subagents {
            if let parentId = sub.parentTaskId, allIds.contains(parentId) {
                childrenByParent[parentId, default: []].append(sub)
            } else {
                roots.append(sub)
            }
        }
        // Sirali (spawnedAt) yapilarini koru.
        let sortedRoots = roots.sorted { $0.spawnedAt < $1.spawnedAt }
        return sortedRoots.map { root in
            buildNode(for: root, childrenByParent: childrenByParent)
        }
    }

    nonisolated private static func buildNode(
        for subagent: Subagent,
        childrenByParent: [String: [Subagent]]
    ) -> SubagentNode {
        let kids = (childrenByParent[subagent.id] ?? [])
            .sorted { $0.spawnedAt < $1.spawnedAt }
        if kids.isEmpty {
            return SubagentNode(subagent: subagent, children: nil)
        }
        return SubagentNode(
            subagent: subagent,
            children: kids.map { buildNode(for: $0, childrenByParent: childrenByParent) }
        )
    }
}
