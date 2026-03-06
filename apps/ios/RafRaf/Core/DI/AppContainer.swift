import Factory
import Foundation

/// Uygulama genelinde dependency injection container.
/// Factory kutuphanesi ile tum servislerin kaydi burada yapilir.
extension Container {

    // MARK: - Networking

    /// Ag istemcisi.
    var networkClient: Factory<NetworkClient> {
        self { NetworkClient(authInterceptor: self.authInterceptor()) }
            .singleton
    }

    /// WebSocket mesaj yonlendiricisi.
    var webSocketMessageRouter: Factory<WebSocketMessageRouter> {
        self { WebSocketMessageRouter() }
            .singleton
    }

    /// WebSocket istemcisi.
    var webSocketClient: Factory<WebSocketClient> {
        self {
            let keychain = self.keychainHelper()
            return WebSocketClient(
                messageRouter: self.webSocketMessageRouter(),
                tokenProvider: { keychain.readString(for: "auth_access_token") }
            )
        }
        .singleton
    }

    /// WebSocket baglanti yoneticisi.
    var webSocketConnectionManager: Factory<WebSocketConnectionManager> {
        self { @MainActor in WebSocketConnectionManager(webSocketClient: self.webSocketClient()) }
            .singleton
    }

    // MARK: - Auth Core

    /// Keychain yardimcisi.
    var keychainHelper: Factory<KeychainHelper> {
        self { KeychainHelper() }
            .singleton
    }

    /// Biyometrik dogrulama yoneticisi.
    var biometricAuthManager: Factory<BiometricAuthManager> {
        self { BiometricAuthManager() }
            .singleton
    }

    /// Auth durum yoneticisi.
    var authManager: Factory<AuthManager> {
        self { @MainActor in
            let manager = AuthManager(keychain: self.keychainHelper())
            let repository = self.authRepository()
            manager.tokenRefresher = { refreshToken in
                let token = try await repository.refreshToken(refreshToken: refreshToken)
                return token
            }
            return manager
        }
        .singleton
    }

    /// Auth interceptor.
    var authInterceptor: Factory<AuthInterceptor> {
        self { AuthInterceptor(keychain: self.keychainHelper()) }
            .singleton
    }

    // MARK: - Auth Feature

    /// Auth repository.
    var authRepository: Factory<AuthRepositoryProtocol> {
        self { AuthRepositoryImpl(networkClient: self.networkClient()) }
    }

    /// Auth ViewModel.
    var authViewModel: Factory<AuthViewModel> {
        self { @MainActor in
            let repository = self.authRepository()
            let authManager = self.authManager()
            let biometricManager = self.biometricAuthManager()
            return AuthViewModel(
                loginUseCase: LoginUseCase(repository: repository),
                logoutUseCase: LogoutUseCase(authManager: authManager),
                refreshTokenUseCase: RefreshTokenUseCase(repository: repository),
                biometricLoginUseCase: BiometricLoginUseCase(
                    biometricManager: biometricManager,
                    authManager: authManager
                ),
                authManager: authManager,
                biometricManager: biometricManager
            )
        }
    }

    // MARK: - Chat Feature

    /// Chat repository.
    var chatRepository: Factory<ChatRepositoryProtocol> {
        self {
            ChatRepositoryImpl(
                webSocketClient: self.webSocketClient(),
                networkClient: self.networkClient()
            )
        }
    }

    /// Chat ViewModel.
    var chatViewModel: Factory<ChatViewModel> {
        self { @MainActor in
            let repository = self.chatRepository()
            return ChatViewModel(
                sendMessageUseCase: SendMessageUseCase(repository: repository),
                loadHistoryUseCase: LoadChatHistoryUseCase(repository: repository),
                fetchMissedMessagesUseCase: FetchMissedMessagesUseCase(repository: repository),
                chatRepository: repository
            )
        }
    }

    /// Chat session manager (coklu proje destegi).
    var chatSessionManager: Factory<ChatSessionManager> {
        self { @MainActor in
            ChatSessionManager(
                sendMessageUseCaseFactory: {
                    SendMessageUseCase(repository: self.chatRepository())
                },
                loadHistoryUseCaseFactory: {
                    LoadChatHistoryUseCase(repository: self.chatRepository())
                },
                fetchMissedMessagesUseCaseFactory: {
                    FetchMissedMessagesUseCase(repository: self.chatRepository())
                },
                chatRepositoryFactory: {
                    self.chatRepository()
                }
            )
        }
        .singleton
    }

    // MARK: - Voice Input Feature

    /// Ses oturumu yoneticisi.
    var audioSessionManager: Factory<RFAudioSessionManager> {
        self { RFAudioSessionManager() }
            .singleton
    }

    /// Deepgram STT tanici.
    var speechRecognizer: Factory<RFSpeechRecognizer> {
        self { RFSpeechRecognizer(keychainHelper: self.keychainHelper()) }
            .singleton
    }

    /// Voice input repository.
    var voiceInputRepository: Factory<VoiceInputRepositoryProtocol> {
        self {
            VoiceInputRepositoryImpl(
                speechRecognizer: self.speechRecognizer(),
                audioSessionManager: self.audioSessionManager()
            )
        }
    }

    /// Voice input ViewModel.
    var voiceInputViewModel: Factory<VoiceInputViewModel> {
        self { @MainActor in
            let repository = self.voiceInputRepository()
            return VoiceInputViewModel(
                startRecordingUseCase: StartVoiceRecordingUseCase(repository: repository),
                stopRecordingUseCase: StopVoiceRecordingUseCase(repository: repository),
                audioSessionManager: self.audioSessionManager()
            )
        }
        .singleton
    }

    // MARK: - Voice Conversation Feature

    /// Streaming ses oynatici.
    var streamingAudioPlayer: Factory<StreamingAudioPlayer> {
        self { StreamingAudioPlayer() }
    }

    /// Voice conversation ViewModel.
    var voiceConversationViewModel: Factory<VoiceConversationViewModel> {
        self { @MainActor in
            VoiceConversationViewModel(
                voiceInputVM: self.voiceInputViewModel(),
                webSocketManager: self.webSocketConnectionManager(),
                streamingAudioPlayer: self.streamingAudioPlayer(),
                chatViewModel: self.chatViewModel()
            )
        }
    }

    // MARK: - Voice Output Feature

    /// TTS ses cache yoneticisi.
    var ttsAudioCache: Factory<TTSAudioCache> {
        self { TTSAudioCache() }
            .singleton
    }

    /// Voice output repository.
    var voiceOutputRepository: Factory<VoiceOutputRepositoryProtocol> {
        self {
            VoiceOutputRepositoryImpl(
                networkClient: self.networkClient(),
                cache: self.ttsAudioCache()
            )
        }
    }

    /// Ses oynatici.
    var voiceAudioPlayer: Factory<VoiceAudioPlayerProtocol> {
        self { VoiceAudioPlayer() }
    }

    /// Voice output ViewModel.
    var voiceOutputViewModel: Factory<VoiceOutputViewModel> {
        self { @MainActor in
            let repository = self.voiceOutputRepository()
            let player = self.voiceAudioPlayer()
            return VoiceOutputViewModel(
                synthesizeSpeechUseCase: SynthesizeSpeechUseCase(repository: repository),
                audioPlayer: player
            )
        }
        .singleton
    }

    // MARK: - Approval Feature

    /// Approval repository.
    var approvalRepository: Factory<ApprovalRepositoryProtocol> {
        self {
            ApprovalRepositoryImpl(
                webSocketClient: self.webSocketClient(),
                messageRouter: self.webSocketMessageRouter()
            )
        }
    }

    /// Approval card ViewModel.
    var approvalCardViewModel: Factory<ApprovalCardViewModel> {
        self { @MainActor in
            let repository = self.approvalRepository()
            return ApprovalCardViewModel(
                submitDecisionUseCase: SubmitApprovalDecisionUseCase(
                    repository: repository
                )
            )
        }
    }

    // MARK: - Screenshot Viewer Feature

    /// Screenshot repository.
    var screenshotRepository: Factory<ScreenshotRepositoryProtocol> {
        self { ScreenshotRepositoryImpl(networkClient: self.networkClient()) }
    }

    /// Screenshot viewer ViewModel.
    var screenshotViewerViewModel: Factory<ScreenshotViewerViewModel> {
        self { @MainActor in
            let repository = self.screenshotRepository()
            return ScreenshotViewerViewModel(
                loadScreenshotUseCase: LoadScreenshotUseCase(
                    repository: repository
                )
            )
        }
    }

    // MARK: - File Sharing Feature

    /// File sharing repository.
    var fileRepository: Factory<FileRepositoryProtocol> {
        self { FileRepositoryImpl(networkClient: self.networkClient()) }
    }

    /// File picker ViewModel.
    var filePickerViewModel: Factory<FilePickerViewModel> {
        self { @MainActor in
            let repository = self.fileRepository()
            return FilePickerViewModel(
                uploadFileUseCase: UploadFileUseCase(repository: repository),
                downloadFileUseCase: DownloadFileUseCase(repository: repository)
            )
        }
    }

    // MARK: - Notifications Feature

    /// Push bildirim yoneticisi.
    var pushNotificationManager: Factory<PushNotificationManager> {
        self { @MainActor in PushNotificationManager() }
            .singleton
    }

    /// Notification repository.
    var notificationRepository: Factory<NotificationRepositoryProtocol> {
        self { NotificationRepositoryImpl(networkClient: self.networkClient()) }
    }

    /// Notification settings ViewModel.
    var notificationSettingsViewModel: Factory<NotificationSettingsViewModel> {
        self { @MainActor in
            let repository = self.notificationRepository()
            let manager = self.pushNotificationManager()
            return NotificationSettingsViewModel(
                registerDeviceTokenUseCase: RegisterDeviceTokenUseCase(
                    repository: repository
                ),
                notificationManager: manager,
                repository: repository
            )
        }
    }

    // MARK: - Progress Feature

    /// Progress repository.
    var progressRepository: Factory<ProgressRepositoryProtocol> {
        self { ProgressRepositoryImpl() }
            .singleton
    }

    /// Progress ViewModel.
    var progressViewModel: Factory<ProgressViewModel> {
        self { @MainActor in
            let repository = self.progressRepository()
            return ProgressViewModel(
                observeProgressUseCase: ObserveProgressUseCase(repository: repository)
            )
        }
        .singleton
    }

    // MARK: - Project Feature

    /// Project repository.
    var projectRepository: Factory<ProjectStatusRepositoryProtocol> {
        self { ProjectRepositoryImpl(networkClient: self.networkClient()) }
    }

    /// Project list ViewModel.
    var projectListViewModel: Factory<ProjectListViewModel> {
        self { @MainActor in
            let repository = self.projectRepository()
            let agentRepository = self.agentRepository()
            return ProjectListViewModel(
                getProjectsUseCase: GetProjectsUseCase(repository: repository),
                updateProjectStatusUseCase: UpdateProjectStatusUseCase(repository: repository),
                getAgentsUseCase: GetAgentsUseCase(repository: agentRepository)
            )
        }
    }

    // MARK: - Agent Feature

    /// Agent repository.
    var agentRepository: Factory<AgentRepositoryProtocol> {
        self { AgentRepositoryImpl(networkClient: self.networkClient()) }
    }

    /// Agent list ViewModel.
    var agentListViewModel: Factory<AgentListViewModel> {
        self { @MainActor in
            let repository = self.agentRepository()
            return AgentListViewModel(
                getAgentsUseCase: GetAgentsUseCase(repository: repository),
                getSubscriptionUsageUseCase: GetSubscriptionUsageUseCase(repository: repository),
                refreshSubscriptionUsageUseCase: RefreshSubscriptionUsageUseCase(repository: repository),
                getAgentProjectsUseCase: GetAgentProjectsUseCase(repository: repository),
                setProjectActiveUseCase: SetProjectActiveUseCase(repository: repository),
                getClaudeProcessesUseCase: GetClaudeProcessesUseCase(repository: repository),
                getAgentTasksUseCase: GetAgentTasksUseCase(repository: repository),
                cancelAgentTaskUseCase: CancelAgentTaskUseCase(repository: repository),
                dispatchAgentTaskUseCase: DispatchAgentTaskUseCase(repository: repository),
                rescanProjectsUseCase: RescanProjectsUseCase(repository: repository),
                getSkipPermissionsUseCase: GetAgentSkipPermissionsUseCase(repository: repository),
                updateSettingsUseCase: UpdateAgentSettingsUseCase(repository: repository)
            )
        }
    }

    // MARK: - Settings Feature

    /// Settings repository.
    var settingsRepository: Factory<SettingsRepositoryProtocol> {
        self { SettingsRepositoryImpl() }
            .singleton
    }

    /// User profile repository.
    var userRepository: Factory<UserRepositoryProtocol> {
        self { UserRepositoryImpl(networkClient: self.networkClient()) }
    }

    /// Settings ViewModel.
    var settingsViewModel: Factory<SettingsViewModel> {
        self { @MainActor in
            let settingsRepo = self.settingsRepository()
            let userRepo = self.userRepository()
            let authManager = self.authManager()
            return SettingsViewModel(
                loadSettingsUseCase: LoadSettingsUseCase(repository: settingsRepo),
                saveSettingsUseCase: SaveSettingsUseCase(repository: settingsRepo),
                loadProfileUseCase: LoadProfileUseCase(repository: userRepo),
                updateProfileUseCase: UpdateProfileUseCase(repository: userRepo),
                logoutUseCase: LogoutUseCase(authManager: authManager)
            )
        }
    }
}
