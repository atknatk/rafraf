import Factory
import Foundation

/// Coklu proje bazli chat session yoneticisi.
/// Her proje icin ayri ChatViewModel tutar, lazy olusturur.
@Observable
@MainActor
final class ChatSessionManager {
    // MARK: - State

    /// Aktif proje ID'si (nil = genel sohbet).
    var activeProjectId: String?

    /// Aktif proje adi (UI'da gosterilir).
    var activeProjectName: String?

    // MARK: - Private

    private var viewModels: [String: ChatViewModel] = [:]
    private let sendMessageUseCaseFactory: () -> SendMessageUseCase
    private let loadHistoryUseCaseFactory: () -> LoadChatHistoryUseCase

    // MARK: - Init

    init(
        sendMessageUseCaseFactory: @escaping () -> SendMessageUseCase,
        loadHistoryUseCaseFactory: @escaping () -> LoadChatHistoryUseCase
    ) {
        self.sendMessageUseCaseFactory = sendMessageUseCaseFactory
        self.loadHistoryUseCaseFactory = loadHistoryUseCaseFactory
    }

    // MARK: - Public

    /// Aktif projenin ChatViewModel'ini dondurur.
    var activeViewModel: ChatViewModel {
        viewModel(for: activeProjectId)
    }

    /// Belirli bir proje icin ChatViewModel dondurur (lazy creation).
    func viewModel(for projectId: String?) -> ChatViewModel {
        let key = projectId ?? "_global"
        if let existing = viewModels[key] {
            return existing
        }
        let vm = ChatViewModel(
            sendMessageUseCase: sendMessageUseCaseFactory(),
            loadHistoryUseCase: loadHistoryUseCaseFactory(),
            projectId: projectId
        )
        viewModels[key] = vm
        return vm
    }

    /// Aktif projeyi degistirir.
    func switchProject(id: String?, name: String?) {
        activeProjectId = id
        activeProjectName = name
    }
}
