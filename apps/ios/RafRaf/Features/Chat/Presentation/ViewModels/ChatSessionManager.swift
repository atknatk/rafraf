import Factory
import Foundation
import os
import UIKit

/// Coklu proje bazli chat session yoneticisi.
/// Her (agentId, projectId) kombinasyonu icin ayri ChatViewModel tutar, lazy olusturur.
@Observable
@MainActor
final class ChatSessionManager {
    // MARK: - State

    /// Aktif proje ID'si (nil = genel sohbet).
    var activeProjectId: String?

    /// Aktif proje adi (UI'da gosterilir).
    var activeProjectName: String?

    /// Aktif agent ID'si (nil = agent secilmedi).
    var activeAgentId: String?

    // MARK: - Private

    private var viewModels: [String: ChatViewModel] = [:]
    private let sendMessageUseCaseFactory: () -> SendMessageUseCase
    private let loadHistoryUseCaseFactory: () -> LoadChatHistoryUseCase
    private let fetchMissedMessagesUseCaseFactory: () -> FetchMissedMessagesUseCase
    private let chatRepositoryFactory: (() -> any ChatRepositoryProtocol)?
    private let logger = AppLogger.logger(for: "ChatSessionManager")

    // MARK: - Init

    init(
        sendMessageUseCaseFactory: @escaping () -> SendMessageUseCase,
        loadHistoryUseCaseFactory: @escaping () -> LoadChatHistoryUseCase,
        fetchMissedMessagesUseCaseFactory: @escaping () -> FetchMissedMessagesUseCase,
        chatRepositoryFactory: (() -> any ChatRepositoryProtocol)? = nil
    ) {
        self.sendMessageUseCaseFactory = sendMessageUseCaseFactory
        self.loadHistoryUseCaseFactory = loadHistoryUseCaseFactory
        self.fetchMissedMessagesUseCaseFactory = fetchMissedMessagesUseCaseFactory
        self.chatRepositoryFactory = chatRepositoryFactory
        registerMemoryPressureObserver()
    }

    // NOTE: explicit `deinit` ile observer remove etmek @MainActor ile uyumsuz
    // (Swift 6 nonisolated deinit'ten property erisimini engeller). Observer
    // closure `[weak self]` capture eder; self deallocate olunca callback no-op
    // olur (NotificationCenter weak referans tutmasa da closure'in icindeki
    // self gone). Ek olarak `ChatSessionManager` singleton oldugu icin gercek
    // dunyada deinit calismaz.

    // MARK: - Public

    /// Aktif projenin ChatViewModel'ini dondurur.
    var activeViewModel: ChatViewModel {
        viewModel(for: activeProjectId, agentId: activeAgentId)
    }

    /// Belirli bir (agentId, projectId) kombinasyonu icin ChatViewModel dondurur (lazy creation).
    func viewModel(for projectId: String?, agentId: String? = nil) -> ChatViewModel {
        let key = "\(agentId ?? "_noagent"):\(projectId ?? "_global")"
        if let existing = viewModels[key] {
            return existing
        }
        let vm = ChatViewModel(
            sendMessageUseCase: sendMessageUseCaseFactory(),
            loadHistoryUseCase: loadHistoryUseCaseFactory(),
            fetchMissedMessagesUseCase: fetchMissedMessagesUseCaseFactory(),
            chatRepository: chatRepositoryFactory?(),
            projectId: projectId,
            agentId: agentId
        )
        viewModels[key] = vm
        return vm
    }

    /// Aktif projeyi ve agent'i degistirir.
    func switchProject(id: String?, name: String?, agentId: String? = nil) {
        activeProjectId = id
        activeProjectName = name
        activeAgentId = agentId
    }

    /// Mesajin ait oldugu ViewModel'i metadata'dan bulur.
    /// projectId yoksa aktif ViewModel'e yonlendirir.
    func viewModelForMessage(projectId: String?, agentId: String?) -> ChatViewModel {
        if let projectId {
            return viewModel(for: projectId, agentId: agentId)
        }
        return activeViewModel
    }

    /// Tum aktif viewmodel'ler icin kacirilmis mesajlari getirir.
    /// WebSocket reconnect veya app foreground'a donunce cagirilir.
    func fetchMissedMessagesForAll() async {
        for vm in viewModels.values {
            await vm.fetchMissedMessages()
        }
    }

    // MARK: - Memory Pressure (Item 5)

    /// Aktif (gorunur) ChatViewModel anahtarini turetir.
    /// Memory-pressure eviction sirasinda bu anahtardaki VM korunur.
    private var activeKey: String {
        "\(activeAgentId ?? "_noagent"):\(activeProjectId ?? "_global")"
    }

    private func registerMemoryPressureObserver() {
        // `UIApplication.didReceiveMemoryWarningNotification` arka planda
        // tetiklenebilir; main actor'a gec ve LRU eviction'i orada calistir.
        // Observer reference'i tutmuyoruz cunku ChatSessionManager singleton —
        // process boyunca yasiyor; cleanup gerekmiyor.
        NotificationCenter.default.addObserver(
            forName: UIApplication.didReceiveMemoryWarningNotification,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            // Closure nonisolated; main queue'da geldigi icin guvenle MainActor'a teleport.
            Task { @MainActor [weak self] in
                self?.handleMemoryPressure()
            }
        }
    }

    /// Memory pressure altinda inactive (gorunur olmayan) sessionlari evict eder.
    ///
    /// Politika:
    ///   - Aktif (gorunur) ChatViewModel'in mesajlari KORUNUR.
    ///   - Diger (inactive) ChatViewModel'lerden eski yarisi atilir; her
    ///     session'da en az `ChatViewModel.lruMinimumRetainedMessages` mesaj
    ///     korunur (bkz. `ChatViewModel.evictOldestMessages`).
    ///   - Yukari kaydirma jest'inde `loadMoreMessages` REST'ten eski
    ///     mesajlari yeniden cekecek (eviction `hasMoreMessages = true` set eder).
    func handleMemoryPressure() {
        let activeKey = self.activeKey
        var totalEvicted = 0
        for (key, vm) in viewModels where key != activeKey {
            totalEvicted += vm.evictOldestMessages()
        }
        if totalEvicted > 0 {
            logger.warning("Memory pressure: \(totalEvicted) inactive mesaj evict edildi")
        }
    }

    /// Bir session'i tamamen baseline'a sifirlar (kullanici farkli bir
    /// projeye gecmis ve uzun sure geri donmemis ise cagirilabilir).
    func resetInactiveSession(agentId: String?, projectId: String?) {
        let key = "\(agentId ?? "_noagent"):\(projectId ?? "_global")"
        guard key != activeKey else { return } // aktif sesion sifirlanmaz
        viewModels[key]?.resetForInactiveSession()
    }
}
