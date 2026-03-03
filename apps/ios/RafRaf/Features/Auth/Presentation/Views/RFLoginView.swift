import SwiftUI

/// Login ekrani.
/// Email + sifre ile giris ve biyometrik dogrulama secenegi sunar.
struct RFLoginView: View {
    @Bindable var viewModel: AuthViewModel

    var body: some View {
        GeometryReader { geometry in
            ScrollView {
                VStack(spacing: RFSpacing.xl) {
                    // Logo ve baslik
                    headerSection

                    // Giris formu
                    loginFormSection

                    // Giris butonu
                    loginButtonSection

                    // Biyometrik giris
                    if viewModel.isBiometricAvailable {
                        biometricSection
                    }

                    // Hata mesaji
                    if let errorMessage = viewModel.errorMessage {
                        RFText(
                            errorMessage,
                            style: .caption,
                            color: RFColors.error
                        )
                    }

                    // Register yonlendirmesi
                    registerLinkSection
                }
                .padding(.horizontal, RFSpacing.xl)
                .frame(minHeight: geometry.size.height)
                .frame(maxWidth: .infinity)
            }
        }
    }

    // MARK: - Sections

    @ViewBuilder
    private var headerSection: some View {
        VStack(spacing: RFSpacing.sm) {
            Image(systemName: "lock.shield.fill")
                .font(.system(size: 60))
                .foregroundStyle(RFColors.fallbackPrimary)

            RFText(
                String(localized: "auth.login.title"),
                style: .largeTitle
            )

            RFText(
                String(localized: "auth.login.subtitle"),
                style: .body,
                color: RFColors.fallbackTextSecondary
            )
        }
        .padding(.top, RFSpacing.md)
    }

    @ViewBuilder
    private var loginFormSection: some View {
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
            .textContentType(.password)
        }
    }

    @ViewBuilder
    private var loginButtonSection: some View {
        RFButton(
            String(localized: "auth.login.button"),
            style: .primary,
            size: .large,
            isLoading: viewModel.isLoading,
            isDisabled: !viewModel.isLoginFormValid
        ) {
            Task {
                await viewModel.login()
            }
        }
    }

    @ViewBuilder
    private var biometricSection: some View {
        VStack(spacing: RFSpacing.sm) {
            dividerWithText(String(localized: "auth.login.orDivider"))

            RFBiometricButton(
                biometricType: viewModel.biometricType,
                isLoading: viewModel.isLoading
            ) {
                Task {
                    await viewModel.loginWithBiometric()
                }
            }
        }
    }

    @ViewBuilder
    private var registerLinkSection: some View {
        HStack(spacing: RFSpacing.xxs) {
            RFText(
                String(localized: "auth.login.noAccount"),
                style: .body,
                color: RFColors.fallbackTextSecondary
            )

            RFButton(
                String(localized: "auth.login.registerLink"),
                style: .ghost,
                size: .small
            ) {
                viewModel.toggleAuthMode()
            }
        }
    }

    // MARK: - Helpers

    @ViewBuilder
    private func dividerWithText(_ text: String) -> some View {
        HStack {
            Rectangle()
                .fill(RFColors.divider)
                .frame(height: 1)

            RFText(text, style: .caption, color: RFColors.fallbackTextSecondary)

            Rectangle()
                .fill(RFColors.divider)
                .frame(height: 1)
        }
    }
}

#Preview {
    RFLoginView(
        viewModel: AuthViewModel(
            loginUseCase: LoginUseCase(
                repository: PreviewAuthRepository()
            ),
            logoutUseCase: LogoutUseCase(authManager: AuthManager()),
            refreshTokenUseCase: RefreshTokenUseCase(
                repository: PreviewAuthRepository()
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
private struct PreviewAuthRepository: AuthRepositoryProtocol {
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
