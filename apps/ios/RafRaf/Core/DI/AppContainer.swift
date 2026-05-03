import Factory
import Foundation

/// Uygulama genelinde dependency injection container.
/// Factory kutuphanesi ile tum servislerin kaydi burada yapilir.
extension Container {

    // MARK: - Networking

    /// Ag istemcisi.
    var networkClient: Factory<NetworkClient> {
        self {
            // Note: tokenRefreshHandler cannot use authManager here
            // because AuthManager -> AuthRepository -> NetworkClient (circular).
            // Instead, we do a lightweight refresh using a dedicated NetworkClient.
            let keychain = self.keychainHelper()
            return NetworkClient(
                authInterceptor: self.authInterceptor(),
                tokenRefreshHandler: { @Sendable in
                    // Read refresh token from Keychain
                    guard let refreshToken = keychain.readString(for: "auth_refresh_token") else {
                        return false
                    }
                    // Use a separate NetworkClient (no auth interceptor) to call refresh
                    let plainClient = NetworkClient()
                    do {
                        let response: TokenResponseDTO = try await plainClient.post(
                            path: "/auth/refresh",
                            body: RefreshRequestDTO(refreshToken: refreshToken)
                        )
                        // Save new tokens to keychain
                        try keychain.saveString(response.accessToken, for: "auth_access_token")
                        try keychain.saveString(response.refreshToken, for: "auth_refresh_token")
                        let expiresAt = Date().addingTimeInterval(TimeInterval(response.expiresIn))
                        try keychain.saveString(
                            ISO8601DateFormatter().string(from: expiresAt),
                            for: "auth_token_expires_at"
                        )
                        return true
                    } catch {
                        return false
                    }
                }
            )
        }
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
                tokenProvider: { keychain.readString(for: "auth_access_token") },
                tokenRefreshHandler: { @Sendable in
                    guard let refreshToken = keychain.readString(for: "auth_refresh_token") else {
                        return false
                    }
                    let plainClient = NetworkClient()
                    do {
                        let response: TokenResponseDTO = try await plainClient.post(
                            path: "/auth/refresh",
                            body: RefreshRequestDTO(refreshToken: refreshToken)
                        )
                        try keychain.saveString(response.accessToken, for: "auth_access_token")
                        try keychain.saveString(response.refreshToken, for: "auth_refresh_token")
                        let expiresAt = Date().addingTimeInterval(TimeInterval(response.expiresIn))
                        try keychain.saveString(
                            ISO8601DateFormatter().string(from: expiresAt),
                            for: "auth_token_expires_at"
                        )
                        return true
                    } catch {
                        return false
                    }
                }
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

    // MARK: - Home Feature

    /// Session AI baslik guncellemeleri repository'si (T1.8).
    /// Singleton — WebSocket router handler ve view model'ler ayni instance'a baglanir.
    var sessionTitleRepository: Factory<SessionTitleRepositoryImpl> {
        self { SessionTitleRepositoryImpl() }
            .singleton
    }

    /// `session.title` mesajlari icin WebSocket handler'i (T1.8).
    /// `WebSocketConnectionManager` baglandiktan sonra router'a kaydedilir.
    var sessionTitleMessageHandler: Factory<SessionTitleMessageHandler> {
        self {
            SessionTitleMessageHandler(repository: self.sessionTitleRepository())
        }
        .singleton
    }

    /// Home feature ViewModel.
    var homeViewModel: Factory<HomeViewModel> {
        self { @MainActor in
            HomeViewModel(
                observeSessionTitleUpdatesUseCase: ObserveSessionTitleUpdatesUseCase(
                    repository: self.sessionTitleRepository()
                ),
                loadRecentChatUseCase: LoadRecentChatUseCase(
                    repository: self.chatRepository()
                )
            )
        }
    }

    // MARK: - Approval Feature

    /// V1.x ship blocker fix — backend `ack` envelope inbox'i.
    /// Singleton: `ApprovalRepositoryImpl` (gonderim) ve
    /// `ApprovalDeliveryAckMessageHandler` (alim) ayni instance'i paylasmali
    /// ki ack envelope geldiginde dogru continuation cozulsun.
    var approvalDeliveryAckInbox: Factory<ApprovalDeliveryAckInbox> {
        self { ApprovalDeliveryAckInbox() }
            .singleton
    }

    /// Approval repository.
    var approvalRepository: Factory<ApprovalRepositoryProtocol> {
        self {
            ApprovalRepositoryImpl(
                webSocketClient: self.webSocketClient(),
                messageRouter: self.webSocketMessageRouter(),
                ackInbox: self.approvalDeliveryAckInbox()
            )
        }
    }

    /// V1.x ship blocker fix — `ack` envelope WebSocket router handler'i.
    /// Singleton — inbox ile ayni yasam suresi.
    var approvalDeliveryAckMessageHandler: Factory<ApprovalDeliveryAckMessageHandler> {
        self {
            ApprovalDeliveryAckMessageHandler(inbox: self.approvalDeliveryAckInbox())
        }
        .singleton
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

    /// V1.5 — Backend-originated approval question presenter.
    /// Singleton: WebSocketMessageRouter handler ve root ContentView ayni
    /// instance'a baglanir, queue durumu process boyunca tek noktada tutulur.
    var approvalCoordinator: Factory<ApprovalCoordinator> {
        self { @MainActor in
            ApprovalCoordinator(
                submitDecisionUseCase: SubmitApprovalDecisionUseCase(
                    repository: self.approvalRepository()
                )
            )
        }
        .singleton
    }

    /// V1.5 — `question` mesaji icin WebSocket router handler'i.
    /// Singleton — coordinator gibi process-wide tek instance.
    var approvalQuestionMessageHandler: Factory<ApprovalQuestionMessageHandler> {
        self { @MainActor in
            ApprovalQuestionMessageHandler(coordinator: self.approvalCoordinator())
        }
        .singleton
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

    /// Subagent state repository (Claude Agent Teams subagent tree — T1.7).
    /// Item 9 — `networkClient` enjekte edilir, REST hydration desteklenir.
    var subagentRepository: Factory<SubagentRepository> {
        self { SubagentRepositoryImpl(networkClient: self.networkClient()) }
            .singleton
    }

    /// Subagent gozlemleme use case'i.
    var observeSubagentsUseCase: Factory<ObserveSubagentsUseCase> {
        self { ObserveSubagentsUseCase(repository: self.subagentRepository()) }
    }

    /// Subagent tree ViewModel — her acilista yeni instance (per-session scope).
    var subagentTreeViewModel: Factory<SubagentTreeViewModel> {
        self { @MainActor in
            SubagentTreeViewModel(observeUseCase: self.observeSubagentsUseCase())
        }
    }

    // MARK: - Claude Subprocess Supervisor (V1.x SLIM — Item 11)

    /// Lokal bildirim factory'si — stalled / crashed / rate_limited durumlarinda
    /// 1 adet OS-level banner planlar (de-dupe by sessionId).
    var claudeProcessNotificationFactory: Factory<ClaudeProcessNotificationFactoryProtocol> {
        self { ClaudeProcessNotificationFactory() }
            .singleton
    }

    /// Supervise edilen claude subprocess repository'si.
    /// Singleton: WS handler'lari ve banner ayni in-memory state'i paylasmali.
    var claudeProcessRepository: Factory<ClaudeProcessRepository> {
        self {
            ClaudeProcessRepositoryImpl(
                webSocketClient: self.webSocketClient(),
                notificationFactory: self.claudeProcessNotificationFactory()
            )
        }
        .singleton
    }

    /// Banner Retry butonu use case'i.
    var retryClaudeProcessUseCase: Factory<RetryClaudeProcessUseCase> {
        self { RetryClaudeProcessUseCase(repository: self.claudeProcessRepository()) }
    }

    /// Banner stream gozlemleme use case'i.
    var observeClaudeProcessBannerUseCase: Factory<ObserveClaudeProcessBannerUseCase> {
        self { ObserveClaudeProcessBannerUseCase(repository: self.claudeProcessRepository()) }
    }

    /// V1.x SLIM — 6 inbound `event.claude.process.*` mesajlarini repository'ye
    /// tasiyan WS handler'larin koleksiyonu (ContentView app start'inda router'a
    /// register edilir).
    var claudeProcessMessageHandlers: Factory<ClaudeProcessMessageHandlerSet> {
        self {
            let repo = self.claudeProcessRepository()
            return ClaudeProcessMessageHandlerSet(
                spawned: ClaudeProcessSpawnedHandler(repository: repo),
                healthcheck: ClaudeProcessHealthcheckHandler(repository: repo),
                stalled: ClaudeProcessStalledHandler(repository: repo),
                crashed: ClaudeProcessCrashedHandler(repository: repo),
                recovered: ClaudeProcessRecoveredHandler(repository: repo),
                diagnosed: ClaudeProcessDiagnosedHandler(repository: repo)
            )
        }
        .singleton
    }

    // MARK: - Proactive Notifications Feature

    /// Proaktif bildirim repository.
    var proactiveNotificationRepository: Factory<ProactiveNotificationRepositoryProtocol> {
        self { ProactiveNotificationRepositoryImpl(networkClient: self.networkClient()) }
    }

    /// Bildirim merkezi ViewModel.
    var notificationCenterViewModel: Factory<NotificationCenterViewModel> {
        self { @MainActor in
            let repository = self.proactiveNotificationRepository()
            return NotificationCenterViewModel(
                fetchNotificationsUseCase: FetchNotificationsUseCase(repository: repository),
                markNotificationReadUseCase: MarkNotificationReadUseCase(repository: repository),
                repository: repository
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
            let biometricManager = self.biometricAuthManager()
            return SettingsViewModel(
                loadSettingsUseCase: LoadSettingsUseCase(repository: settingsRepo),
                saveSettingsUseCase: SaveSettingsUseCase(repository: settingsRepo),
                loadProfileUseCase: LoadProfileUseCase(repository: userRepo),
                updateProfileUseCase: UpdateProfileUseCase(repository: userRepo),
                logoutUseCase: LogoutUseCase(authManager: authManager),
                authManager: authManager,
                biometricManager: biometricManager
            )
        }
    }
}
