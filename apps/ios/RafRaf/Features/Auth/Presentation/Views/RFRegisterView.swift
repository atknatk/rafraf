import SwiftUI

/// Register ekrani.
/// Yeni kullanici kaydi icin email, sifre ve sifre tekrari alir.
/// Hero gradient arkaplan ve glass kart formu ile premium gorunum.
struct RFRegisterView: View {
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

                    registerFormSection
                        .opacity(isAppeared ? 1 : 0)
                        .offset(y: isAppeared ? 0 : 20)
                        .animation(RFAnimation.springResponsive.delay(0.2), value: isAppeared)

                    registerButtonSection
                        .opacity(isAppeared ? 1 : 0)
                        .offset(y: isAppeared ? 0 : 20)
                        .animation(RFAnimation.springResponsive.delay(0.3), value: isAppeared)

                    if let errorMessage = viewModel.errorMessage {
                        RFText(
                            errorMessage,
                            style: .caption,
                            color: RFColors.error
                        )
                    }

                    loginLinkSection
                        .opacity(isAppeared ? 1 : 0)
                        .animation(RFAnimation.springResponsive.delay(0.35), value: isAppeared)
                }
                .padding(RFSpacing.xl)
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

                Image(systemName: "person.badge.plus.fill")
                    .font(.system(size: 40))
                    .foregroundStyle(RFColors.fallbackPrimary)
                    .symbolEffect(.pulse, options: .repeating.speed(0.3))
            }

            RFText(
                String(localized: "auth.register.title"),
                style: .display
            )

            RFText(
                String(localized: "auth.register.subtitle"),
                style: .bodyLarge,
                color: RFColors.fallbackTextSecondary
            )
        }
        .padding(.top, RFSpacing.xxxl)
    }

    @ViewBuilder
    private var registerFormSection: some View {
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
                .textContentType(.newPassword)

                RFTextField(
                    String(localized: "auth.field.confirmPassword"),
                    text: $viewModel.confirmPassword,
                    mode: .secure,
                    errorMessage: passwordMismatchError,
                    leadingIcon: "lock"
                )
                .textContentType(.newPassword)
            }
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
