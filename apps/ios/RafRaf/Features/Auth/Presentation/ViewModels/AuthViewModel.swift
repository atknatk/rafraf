import Foundation
import os

/// Auth ekranlari ViewModel.
/// Login, register ve biyometrik giris islemlerini yonetir.
@Observable
@MainActor
final class AuthViewModel {
    // MARK: - State

    /// E-posta girisi.
    var email: String = ""
    /// Sifre girisi.
    var password: String = ""
    /// Sifre tekrari (register icin).
    var confirmPassword: String = ""
    /// Yukleme durumu.
    var isLoading: Bool = false
    /// Hata mesaji.
    var errorMessage: String?
    /// Login mi yoksa register ekrani mi gosteriliyor.
    var isShowingRegister: Bool = false
    /// Biyometrik dogrulama mevcut mu.
    var isBiometricAvailable: Bool = false
    /// Biyometrik dogrulama tipi.
    var biometricType: BiometricType = .none
    /// Face ID kurulum uyarisi gosteriliyor mu.
    var showBiometricSetupPrompt: Bool = false

    // MARK: - Private

    private let loginUseCase: LoginUseCase
    private let logoutUseCase: LogoutUseCase
    private let refreshTokenUseCase: RefreshTokenUseCase
    private let biometricLoginUseCase: BiometricLoginUseCase
    private let authManager: AuthManager
    private let biometricManager: BiometricAuthManager
    private let logger = AppLogger.logger(for: "AuthViewModel")

    // MARK: - Init

    init(
        loginUseCase: LoginUseCase,
        logoutUseCase: LogoutUseCase,
        refreshTokenUseCase: RefreshTokenUseCase,
        biometricLoginUseCase: BiometricLoginUseCase,
        authManager: AuthManager,
        biometricManager: BiometricAuthManager
    ) {
        self.loginUseCase = loginUseCase
        self.logoutUseCase = logoutUseCase
        self.refreshTokenUseCase = refreshTokenUseCase
        self.biometricLoginUseCase = biometricLoginUseCase
        self.authManager = authManager
        self.biometricManager = biometricManager

        self.isBiometricAvailable = biometricManager.isBiometricAvailable
        self.biometricType = biometricManager.availableBiometricType
    }

    // MARK: - Computed

    /// Biyometrik dogrulama aktif mi.
    var isBiometricEnabled: Bool {
        authManager.isBiometricEnabled
    }

    // MARK: - Validation

    /// Email formatini dogrular.
    var isEmailValid: Bool {
        let emailRegex = /^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/
        return email.wholeMatch(of: emailRegex) != nil
    }

    /// Sifre uzunlugunu dogrular.
    var isPasswordValid: Bool {
        password.count >= 6
    }

    /// Login formu gecerli mi.
    var isLoginFormValid: Bool {
        isEmailValid && isPasswordValid
    }

    /// Register formu gecerli mi.
    var isRegisterFormValid: Bool {
        isEmailValid && isPasswordValid && password == confirmPassword && !confirmPassword.isEmpty
    }

    // MARK: - Actions

    /// Login islemini baslatir.
    func login() async {
        guard isLoginFormValid else {
            errorMessage = String(localized: "auth.error.invalidForm")
            return
        }

        isLoading = true
        errorMessage = nil

        do {
            let token = try await loginUseCase.execute(
                email: email,
                password: password
            )
            authManager.saveTokens(
                accessToken: token.accessToken,
                refreshToken: token.refreshToken,
                expiresIn: token.expiresIn
            )
            logger.info("Login basarili")
            clearForm()
            if biometricManager.isBiometricAvailable && !authManager.isBiometricEnabled {
                showBiometricSetupPrompt = true
            }
        } catch {
            logger.error("Login hatasi: \(error.localizedDescription)")
            errorMessage = String(localized: "auth.error.loginFailed")
        }

        isLoading = false
    }

    /// Logout islemini baslatir.
    func logout() {
        logoutUseCase.execute()
        clearForm()
        logger.info("Logout yapildi")
    }

    /// Biyometrik dogrulama ile giris yapar.
    func loginWithBiometric() async {
        isLoading = true
        errorMessage = nil

        do {
            try await biometricLoginUseCase.execute()
            logger.info("Biyometrik giris basarili")
        } catch let error as BiometricError {
            switch error {
            case .cancelled:
                logger.info("Biyometrik dogrulama iptal edildi")
            case .notAvailable, .notEnrolled:
                errorMessage = String(localized: "auth.error.biometricNotAvailable")
            case .authenticationFailed:
                errorMessage = String(localized: "auth.error.biometricFailed")
            case .systemError:
                errorMessage = String(localized: "auth.error.biometricFailed")
            }
        } catch {
            logger.error("Biyometrik giris hatasi: \(error.localizedDescription)")
            errorMessage = String(localized: "auth.error.biometricFailed")
        }

        isLoading = false
    }

    /// Token yenileme islemini baslatir.
    func refreshTokenIfNeeded() async {
        guard let refreshToken = authManager.currentRefreshToken else {
            authManager.clearTokens()
            return
        }

        do {
            let token = try await refreshTokenUseCase.execute(
                refreshToken: refreshToken
            )
            authManager.saveTokens(
                accessToken: token.accessToken,
                refreshToken: token.refreshToken,
                expiresIn: token.expiresIn
            )
            logger.info("Token yenilendi")
        } catch {
            logger.error("Token yenileme hatasi: \(error.localizedDescription)")
            authManager.clearTokens()
        }
    }

    /// Face ID'yi etkinlestirir.
    func enableBiometric() {
        authManager.setBiometricEnabled(true)
        showBiometricSetupPrompt = false
        logger.info("Face ID etkinlestirildi")
    }

    /// Face ID'yi devre disi birakir.
    func disableBiometric() {
        authManager.setBiometricEnabled(false)
        logger.info("Face ID devre disi birakildi")
    }

    /// Login/register arasinda gecis yapar.
    func toggleAuthMode() {
        isShowingRegister.toggle()
        errorMessage = nil
    }

    // MARK: - Private

    private func clearForm() {
        email = ""
        password = ""
        confirmPassword = ""
        errorMessage = nil
    }
}
