import Foundation

/// Session AI baslik guncellemelerini observe eden use case.
///
/// Presentation katmani bu use case uzerinden `SessionTitleUpdate`
/// stream'ine subscribe olur. Repository implementasyonu degistiginde
/// view model dokunulmamis kalir.
struct ObserveSessionTitleUpdatesUseCase: Sendable {
    private let repository: SessionTitleRepositoryProtocol

    init(repository: SessionTitleRepositoryProtocol) {
        self.repository = repository
    }

    /// Yeni baslik guncellemeleri icin stream dondurur.
    func callAsFunction() -> AsyncStream<SessionTitleUpdate> {
        repository.titleUpdates()
    }

    /// Cache'lenmis son guncellemeleri (replay) dondurur.
    func snapshot() async -> [String: SessionTitleUpdate] {
        await repository.snapshot()
    }
}
