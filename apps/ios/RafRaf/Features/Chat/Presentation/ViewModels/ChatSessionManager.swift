import Factory
import Foundation

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
    }

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
}
