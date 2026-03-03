import Factory
import Foundation

/// Uygulama genelinde dependency injection container.
/// Factory kutuphanesi ile tum servislerin kaydi burada yapilir.
extension Container {

    // MARK: - Networking

    /// Ag istemcisi.
    var networkClient: Factory<NetworkClient> {
        self { NetworkClient() }
            .singleton
    }

    /// WebSocket mesaj yonlendiricisi.
    var webSocketMessageRouter: Factory<WebSocketMessageRouter> {
        self { WebSocketMessageRouter() }
            .singleton
    }

    /// WebSocket istemcisi.
    var webSocketClient: Factory<WebSocketClient> {
        self { WebSocketClient(messageRouter: self.webSocketMessageRouter()) }
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
        self { @MainActor in AuthManager(keychain: self.keychainHelper()) }
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
        self { ChatRepositoryImpl(webSocketClient: self.webSocketClient()) }
    }

    /// Chat ViewModel.
    var chatViewModel: Factory<ChatViewModel> {
        self { @MainActor in
            let repository = self.chatRepository()
            return ChatViewModel(
                sendMessageUseCase: SendMessageUseCase(repository: repository),
                loadHistoryUseCase: LoadChatHistoryUseCase(repository: repository)
            )
        }
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
}
