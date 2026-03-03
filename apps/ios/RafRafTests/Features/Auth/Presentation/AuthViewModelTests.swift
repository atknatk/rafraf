import Foundation
import Testing
@testable import RafRaf

/// AuthViewModel testleri.
@Suite("AuthViewModel Tests")
@MainActor
struct AuthViewModelTests {

    private func makeViewModel(
        mockRepo: MockAuthRepository = MockAuthRepository()
    ) -> AuthViewModel {
        let keychainService = "com.rafraf.test.\(UUID().uuidString)"
        let keychain = KeychainHelper(service: keychainService)
        let authManager = AuthManager(keychain: keychain)
        let biometricManager = BiometricAuthManager()

        return AuthViewModel(
            loginUseCase: LoginUseCase(repository: mockRepo),
            logoutUseCase: LogoutUseCase(authManager: authManager),
            refreshTokenUseCase: RefreshTokenUseCase(repository: mockRepo),
            biometricLoginUseCase: BiometricLoginUseCase(
                biometricManager: biometricManager,
                authManager: authManager
            ),
            authManager: authManager,
            biometricManager: biometricManager
        )
    }

    @Test("Baslangic durumu dogru olmali")
    func initialState() {
        let viewModel = makeViewModel()

        #expect(viewModel.email == "")
        #expect(viewModel.password == "")
        #expect(viewModel.confirmPassword == "")
        #expect(viewModel.isLoading == false)
        #expect(viewModel.errorMessage == nil)
        #expect(viewModel.isShowingRegister == false)
    }

    @Test("Email validation dogru calismali")
    func emailValidation() {
        let viewModel = makeViewModel()

        viewModel.email = "invalid"
        #expect(viewModel.isEmailValid == false)

        viewModel.email = "test@example.com"
        #expect(viewModel.isEmailValid == true)

        viewModel.email = ""
        #expect(viewModel.isEmailValid == false)

        viewModel.email = "user@domain.co"
        #expect(viewModel.isEmailValid == true)
    }

    @Test("Password validation dogru calismali")
    func passwordValidation() {
        let viewModel = makeViewModel()

        viewModel.password = "12345"
        #expect(viewModel.isPasswordValid == false)

        viewModel.password = "123456"
        #expect(viewModel.isPasswordValid == true)

        viewModel.password = ""
        #expect(viewModel.isPasswordValid == false)
    }

    @Test("Login form validation gecersiz email ile false donmeli")
    func loginFormValidationInvalidEmail() {
        let viewModel = makeViewModel()
        viewModel.email = "invalid"
        viewModel.password = "password123"

        #expect(viewModel.isLoginFormValid == false)
    }

    @Test("Login form validation gecerli verilerle true donmeli")
    func loginFormValidationValid() {
        let viewModel = makeViewModel()
        viewModel.email = "test@example.com"
        viewModel.password = "password123"

        #expect(viewModel.isLoginFormValid == true)
    }

    @Test("Register form validation sifre uyusmuyorsa false donmeli")
    func registerFormPasswordMismatch() {
        let viewModel = makeViewModel()
        viewModel.email = "test@example.com"
        viewModel.password = "password123"
        viewModel.confirmPassword = "different"

        #expect(viewModel.isRegisterFormValid == false)
    }

    @Test("Register form validation dogru verilerle true donmeli")
    func registerFormValid() {
        let viewModel = makeViewModel()
        viewModel.email = "test@example.com"
        viewModel.password = "password123"
        viewModel.confirmPassword = "password123"

        #expect(viewModel.isRegisterFormValid == true)
    }

    @Test("Login basarili oldugunda form temizlenmeli")
    func loginSuccessCleanForm() async {
        let mockRepo = MockAuthRepository()
        let viewModel = makeViewModel(mockRepo: mockRepo)

        viewModel.email = "test@example.com"
        viewModel.password = "password123"

        await viewModel.login()

        #expect(viewModel.email == "")
        #expect(viewModel.password == "")
        #expect(viewModel.errorMessage == nil)
        #expect(mockRepo.loginCallCount == 1)
    }

    @Test("Login basarisiz oldugunda hata mesaji gostermeli")
    func loginFailureShowsError() async {
        let mockRepo = MockAuthRepository()
        mockRepo.loginResult = .failure(NetworkError.unauthorized)
        let viewModel = makeViewModel(mockRepo: mockRepo)

        viewModel.email = "test@example.com"
        viewModel.password = "wrong"

        await viewModel.login()

        #expect(viewModel.errorMessage != nil)
        #expect(viewModel.isLoading == false)
    }

    @Test("Gecersiz formla login hata mesaji gostermeli")
    func loginInvalidFormShowsError() async {
        let viewModel = makeViewModel()
        viewModel.email = "invalid"
        viewModel.password = "123"

        await viewModel.login()

        #expect(viewModel.errorMessage != nil)
    }

    @Test("toggleAuthMode register ve login arasinda gecis yapmali")
    func toggleAuthMode() {
        let viewModel = makeViewModel()

        #expect(viewModel.isShowingRegister == false)

        viewModel.toggleAuthMode()
        #expect(viewModel.isShowingRegister == true)

        viewModel.toggleAuthMode()
        #expect(viewModel.isShowingRegister == false)
    }

    @Test("toggleAuthMode hata mesajini temizlemeli")
    func toggleClearsError() {
        let viewModel = makeViewModel()
        viewModel.errorMessage = "Some error"

        viewModel.toggleAuthMode()

        #expect(viewModel.errorMessage == nil)
    }

    @Test("Logout formu temizlemeli")
    func logoutClearsForm() {
        let viewModel = makeViewModel()
        viewModel.email = "test@example.com"
        viewModel.password = "password"

        viewModel.logout()

        #expect(viewModel.email == "")
        #expect(viewModel.password == "")
    }

    @Test("Token yenileme basarili olmali")
    func refreshTokenSuccess() async {
        let mockRepo = MockAuthRepository()
        let keychainService = "com.rafraf.test.\(UUID().uuidString)"
        let keychain = KeychainHelper(service: keychainService)

        // Keychain erisimi kontrol et
        let probe = "probe_\(UUID().uuidString)"
        do {
            try keychain.saveString("test", for: probe)
            try keychain.delete(for: probe)
        } catch {
            // Keychain erisimi yok, test skip
            return
        }

        let authManager = AuthManager(keychain: keychain)

        // Mevcut refresh token kaydet
        authManager.saveTokens(
            accessToken: "old-access",
            refreshToken: "old-refresh",
            expiresIn: 900
        )

        let viewModel = AuthViewModel(
            loginUseCase: LoginUseCase(repository: mockRepo),
            logoutUseCase: LogoutUseCase(authManager: authManager),
            refreshTokenUseCase: RefreshTokenUseCase(repository: mockRepo),
            biometricLoginUseCase: BiometricLoginUseCase(
                biometricManager: BiometricAuthManager(),
                authManager: authManager
            ),
            authManager: authManager,
            biometricManager: BiometricAuthManager()
        )

        await viewModel.refreshTokenIfNeeded()

        #expect(mockRepo.refreshCallCount == 1)
        #expect(authManager.authState == .authenticated)
    }
}
