import SwiftUI

/// Register ekrani.
/// Yeni kullanici kaydi icin email, sifre ve sifre tekrari alir.
struct RFRegisterView: View {
    @Bindable var viewModel: AuthViewModel

    var body: some View {
        ScrollView {
            VStack(spacing: RFSpacing.xl) {
                // Baslik
                headerSection

                // Register formu
                registerFormSection

                // Kayit butonu
                registerButtonSection

                // Hata mesaji
                if let errorMessage = viewModel.errorMessage {
                    RFText(
                        errorMessage,
                        style: .caption,
                        color: RFColors.error
                    )
                }

                // Login yonlendirmesi
                loginLinkSection
            }
            .padding(RFSpacing.xl)
        }
    }

    // MARK: - Sections

    @ViewBuilder
    private var headerSection: some View {
        VStack(spacing: RFSpacing.sm) {
            Image(systemName: "person.badge.plus.fill")
                .font(.system(size: 60))
                .foregroundStyle(RFColors.fallbackPrimary)

            RFText(
                String(localized: "auth.register.title"),
                style: .largeTitle
            )

            RFText(
                String(localized: "auth.register.subtitle"),
                style: .body,
                color: RFColors.fallbackTextSecondary
            )
        }
        .padding(.top, RFSpacing.xxl)
    }

    @ViewBuilder
    private var registerFormSection: some View {
        VStack(spacing: RFSpacing.md) {
            RFTextField(
                String(localized: "auth.field.email"),
                text: $viewModel.email
            )
            .textContentType(.emailAddress)
            .keyboardType(.emailAddress)
            .autocorrectionDisabled()
            .textInputAutocapitalization(.never)

            RFTextField(
                String(localized: "auth.field.password"),
                text: $viewModel.password,
                mode: .secure
            )
            .textContentType(.newPassword)

            RFTextField(
                String(localized: "auth.field.confirmPassword"),
                text: $viewModel.confirmPassword,
                mode: .secure,
                errorMessage: passwordMismatchError
            )
            .textContentType(.newPassword)
        }
    }

    @ViewBuilder
    private var registerButtonSection: some View {
        RFButton(
            String(localized: "auth.register.button"),
            style: .primary,
            size: .large,
            isLoading: viewModel.isLoading,
            isDisabled: !viewModel.isRegisterFormValid
        ) {
            Task {
                await viewModel.login()
            }
        }
    }

    @ViewBuilder
    private var loginLinkSection: some View {
        HStack(spacing: RFSpacing.xxs) {
            RFText(
                String(localized: "auth.register.hasAccount"),
                style: .body,
                color: RFColors.fallbackTextSecondary
            )

            RFButton(
                String(localized: "auth.register.loginLink"),
                style: .ghost,
                size: .small
            ) {
                viewModel.toggleAuthMode()
            }
        }
    }

    // MARK: - Helpers

    private var passwordMismatchError: String? {
        if !viewModel.confirmPassword.isEmpty && viewModel.password != viewModel.confirmPassword {
            return String(localized: "auth.error.passwordMismatch")
        }
        return nil
    }
}

#Preview {
    RFRegisterView(
        viewModel: AuthViewModel(
            loginUseCase: LoginUseCase(
                repository: PreviewRegisterAuthRepository()
            ),
            logoutUseCase: LogoutUseCase(authManager: AuthManager()),
            refreshTokenUseCase: RefreshTokenUseCase(
                repository: PreviewRegisterAuthRepository()
            ),
            biometricLoginUseCase: BiometricLoginUseCase(
                biometricManager: BiometricAuthManager(),
                authManager: AuthManager()
            ),
            authManager: AuthManager(),
            biometricManager: BiometricAuthManager()
        )
    )
}

/// Preview icin mock repository.
private struct PreviewRegisterAuthRepository: AuthRepositoryProtocol {
    func login(email: String, password: String) async throws -> AuthToken {
        AuthToken(
            accessToken: "preview-token",
            refreshToken: "preview-refresh",
            tokenType: "bearer",
            expiresIn: 900,
            expiresAt: Date().addingTimeInterval(900)
        )
    }

    func refreshToken(refreshToken: String) async throws -> AuthToken {
        AuthToken(
            accessToken: "preview-token",
            refreshToken: "preview-refresh",
            tokenType: "bearer",
            expiresIn: 900,
            expiresAt: Date().addingTimeInterval(900)
        )
    }
}
