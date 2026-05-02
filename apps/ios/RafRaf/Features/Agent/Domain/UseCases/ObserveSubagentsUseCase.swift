import Foundation

/// Subagent listesini gozlemleme use case'i.
///
/// SubagentRepository uzerindeki AsyncStream'i ViewModel'in tuketebilecegi
/// sekilde acar. Snapshot + sonraki tum guncellemeleri yayar.
///
/// Doc 10 §6.3.3 — Agent feature subagent tree.
struct ObserveSubagentsUseCase: Sendable {
    private let repository: SubagentRepository

    init(repository: SubagentRepository) {
        self.repository = repository
    }

    /// Belirli session icin subagent stream'ini dondurur.
    func execute(sessionId: String) async -> AsyncStream<[Subagent]> {
        await repository.observeSubagents(sessionId: sessionId)
    }

    /// Tum oturumlardaki subagent'lari birlestiren stream'i dondurur.
    /// AgentDetailView gibi yer-bagimsiz goruntulemelerde kullanilir.
    func executeAll() async -> AsyncStream<[Subagent]> {
        await repository.observeAllSubagents()
    }

    /// Anlik snapshot'i dondurur (test / initial render icin).
    func snapshot(sessionId: String) async -> [Subagent] {
        await repository.currentSubagents(sessionId: sessionId)
    }

    /// Tum oturumlardan birlestirilmis snapshot.
    func snapshotAll() async -> [Subagent] {
        await repository.currentAllSubagents()
    }
}
