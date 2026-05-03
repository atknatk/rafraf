import Foundation
import os

/// Ana sayfa ViewModel.
///
/// Home ekraninin durumunu ve islemlerini yonetir. T1.8 ile birlikte
/// `session.title` (AI tarafindan uretilen baslik) WebSocket eventlerine
/// abone olup session listesindeki baslik alanini canli gunceller.
///
/// Doc 10 §6.3.4.
@Observable
@MainActor
final class HomeViewModel {
    // MARK: - State

    var isLoading: Bool = false
    var errorMessage: String?

    /// Ekranda gosterilen session ozet listesi.
    /// Mevcut iskelette gercek liste kaynagi (REST endpoint) henuz baglanmadi —
    /// bu nedenle baslangic icin in-memory `seedSessions(_:)` ile beslenir.
    /// Bir sessionın `aiTitle` alani `session.title` event'i geldikce guncellenir.
    var sessions: [HomeSession] = []

    /// Tum sessionlardan gelen en son mesaj — home'da "son sohbet" preview kartini besler.
    var lastChat: ChatMessage?

    // MARK: - Private

    private let observeSessionTitleUpdatesUseCase: ObserveSessionTitleUpdatesUseCase?
    private let loadRecentChatUseCase: LoadRecentChatUseCase?
    private let logger = AppLogger.logger(for: "Home")
    /// `nonisolated(unsafe)` — sadece `loadData()` ve `deinit`'ten okunur/yazilir;
    /// ViewModel @MainActor oldugu icin `loadData` zaten serileştirilir, `deinit` ise
    /// referans biter bitmez calisir ve baska bir okuyucu kalmaz.
    private nonisolated(unsafe) var titleObservationTask: Task<Void, Never>?

    // MARK: - Init

    /// Production init — DI tarafindan kullanilir (`AppContainer.homeViewModel`).
    /// `loadRecentChatUseCase` opsiyonel — testlerde stream gozlemi icin
    /// olusturulan ViewModel'lar nil ile cagiratabilir.
    init(
        observeSessionTitleUpdatesUseCase: ObserveSessionTitleUpdatesUseCase,
        loadRecentChatUseCase: LoadRecentChatUseCase? = nil
    ) {
        self.observeSessionTitleUpdatesUseCase = observeSessionTitleUpdatesUseCase
        self.loadRecentChatUseCase = loadRecentChatUseCase
        logger.info("HomeViewModel baslatildi")
    }

    /// Preview / test init — observation devre disi.
    init() {
        self.observeSessionTitleUpdatesUseCase = nil
        self.loadRecentChatUseCase = nil
        logger.info("HomeViewModel baslatildi (gozlemsiz)")
    }

    deinit {
        titleObservationTask?.cancel()
    }

    // MARK: - Actions

    /// Verileri yukler ve `session.title` event'lerine abone olur.
    func loadData() async {
        isLoading = true
        defer { isLoading = false }

        logger.info("Home verileri yukleniyor")
        await startObservingTitleUpdates()
        await loadLastChat()
    }

    /// Tum sessionlardan en son mesaji yukler — home preview kartini besler.
    /// Hata durumunda sessizce no-op (preview opsiyonel, blocking degil).
    func loadLastChat() async {
        guard let useCase = loadRecentChatUseCase else { return }
        do {
            let messages = try await useCase.execute(limit: 1)
            lastChat = messages.last
            logger.info("Son mesaj preview yuklendi: \(messages.count) mesaj")
        } catch {
            logger.error("Son mesaj preview yuklenemedi: \(error.localizedDescription)")
        }
    }

    /// Test/Preview/Seed amacli bir session listesi yerlestirir.
    /// Idempotent — ayni id'li session'lar tekrar yazilir.
    func seedSessions(_ newSessions: [HomeSession]) {
        sessions = newSessions
    }

    /// Bir session icin AI baslik manuel olarak uygulanir (test ve replay icin).
    func applyTitleUpdate(_ update: SessionTitleUpdate) {
        guard let index = sessions.firstIndex(where: { $0.id == update.sessionId }) else {
            logger.debug(
                "session.title alindi ama eslesen session listede yok: \(update.sessionId, privacy: .public)"
            )
            return
        }
        let updated = sessions[index].updatingAITitle(update.aiTitle)
        sessions[index] = updated
        logger.info(
            "session.title uygulandi sessionId=\(update.sessionId, privacy: .public)"
        )
    }

    // MARK: - Private

    private func startObservingTitleUpdates() async {
        guard let useCase = observeSessionTitleUpdatesUseCase else { return }
        // Subscribe oncesi cache'lenmis son updateleri uygula.
        let snapshot = await useCase.snapshot()
        for update in snapshot.values {
            applyTitleUpdate(update)
        }
        guard titleObservationTask == nil else { return }
        titleObservationTask = Task { [weak self] in
            for await update in useCase() {
                await MainActor.run { [weak self] in
                    self?.applyTitleUpdate(update)
                }
            }
        }
    }
}
