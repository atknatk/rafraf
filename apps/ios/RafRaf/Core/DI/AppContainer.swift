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
}
