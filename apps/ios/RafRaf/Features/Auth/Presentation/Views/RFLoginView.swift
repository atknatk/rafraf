import SwiftUI

/// Login ekrani.
/// Email + sifre ile giris ve biyometrik dogrulama secenegi sunar.
/// Hero gradient arkaplan ve glass kart formu ile premium gorunum.
struct RFLoginView: View {
    @Bindable var viewModel: AuthViewModel
    @State private var isAppeared = false

    var body: some View {
        GeometryReader { geometry in
            ScrollView {
                VStack(spacing: RFSpacing.xl) {
                    headerSection
                        .opacity(isAppeared ? 1 : 0)
                        .offset(y: isAppeared ? 0 : 20)
                        .animation(RFAnimation.springResponsive.delay(0.1), value: isAppeared)

                    loginFormSection
                        .opacity(isAppeared ? 1 : 0)
                        .offset(y: isAppeared ? 0 : 20)
                        .animation(RFAnimation.springResponsive.delay(0.2), value: isAppeared)

                    loginButtonSection
                        .opacity(isAppeared ? 1 : 0)
                        .offset(y: isAppeared ? 0 : 20)
                        .animation(RFAnimation.springResponsive.delay(0.3), value: isAppeared)

                    if viewModel.isBiometricAvailable {
                        biometricSection
                            .opacity(isAppeared ? 1 : 0)
                            .animation(RFAnimation.springResponsive.delay(0.35), value: isAppeared)
                    }

                    if let errorMessage = viewModel.errorMessage {
                        RFText(
                            errorMessage,
                            style: .caption,
                            color: RFColors.error
                        )
                    }

                    registerLinkSection
                        .opacity(isAppeared ? 1 : 0)
                        .animation(RFAnimation.springResponsive.delay(0.4), value: isAppeared)
                }
                .padding(.horizontal, RFSpacing.xl)
                .frame(minHeight: geometry.size.height)
                .frame(maxWidth: .infinity)
            }
        }
        .onAppear { isAppeared = true }
        .background(RFAnimatedGradientBackground())
    }

    // MARK: - Sections

    @ViewBuilder
    private var headerSection: some View {
        VStack(spacing: RFSpacing.md) {
            ZStack {
                Circle()
                    .fill(RFColors.fallbackPrimary.opacity(0.1))
                    .frame(width: 88, height: 88)

                Image(systemName: "lock.shield.fill")
                    .font(.system(size: 40))
                    .foregroundStyle(RFColors.fallbackPrimary)
                    .symbolEffect(.pulse, options: .repeating.speed(0.3))
            }

            RFText(
                String(localized: "auth.login.title"),
                style: .display
            )

            RFText(
                String(localized: "auth.login.subtitle"),
                style: .bodyLarge,
                color: RFColors.fallbackTextSecondary
            )
        }
        .padding(.top, RFSpacing.xxxl)
    }

    @ViewBuilder
    private var loginFormSection: some View {
        RFCard(style: .glass, cornerRadius: RFCornerRadius.extraLarge) {
            VStack(spacing: RFSpacing.md) {
                RFTextField(
                    String(localized: "auth.field.email"),
                    text: $viewModel.email,
                    leadingIcon: "envelope"
                )
                .textContentType(.emailAddress)
                .keyboardType(.emailAddress)
                .autocorrectionDisabled()
                .textInputAutocapitalization(.never)

                RFTextField(
                    String(localized: "auth.field.password"),
                    text: $viewModel.password,
                    mode: .secure,
                    leadingIcon: "lock"
                )
                .textContentType(.password)
            }
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
