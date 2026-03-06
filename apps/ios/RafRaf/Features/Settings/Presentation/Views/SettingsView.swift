import SwiftUI

/// Ayarlar ana ekrani.
/// Profil, ses, bildirim, gorunum ve hesap ayarlarini card-based layout ile gosterir.
/// Glass profil karti ve hero gradient arkaplan ile premium gorunum.
struct SettingsView: View {
    @State private var viewModel: SettingsViewModel
    @State private var isAppeared = false

    init(viewModel: SettingsViewModel) {
        self._viewModel = State(initialValue: viewModel)
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: RFSpacing.md) {
                    profileCard
                        .rfEntrance(isAppeared: isAppeared, delay: 0.05)

                    if viewModel.isBiometricAvailable {
                        securityCard
                            .rfEntrance(isAppeared: isAppeared, delay: 0.08)
                    }

                    voiceSettingsCard
                        .rfEntrance(isAppeared: isAppeared, delay: 0.1)

                    notificationSettingsCard
                        .rfEntrance(isAppeared: isAppeared, delay: 0.15)

                    CostSummaryCard()
                        .rfEntrance(isAppeared: isAppeared, delay: 0.18)

                    appearanceSettingsCard
                        .rfEntrance(isAppeared: isAppeared, delay: 0.2)

                    appInfoCard
                        .rfEntrance(isAppeared: isAppeared, delay: 0.25)

                    logoutCard
                        .rfEntrance(isAppeared: isAppeared, delay: 0.3)
                }
                .padding(.horizontal, RFSpacing.md)
                .padding(.vertical, RFSpacing.sm)
            }
            .contentMargins(.bottom, RFSpacing.xxxl)
            .background(
                LinearGradient(
                    colors: [RFColors.heroGradientStart, RFColors.heroGradientEnd],
                    startPoint: .top,
                    endPoint: .bottom
                )
                .ignoresSafeArea()
            )
            .navigationTitle(String(localized: "settings.title"))
            .alert(
                String(localized: "settings.logout.confirmTitle"),
                isPresented: $viewModel.isShowingLogoutConfirmation
            ) {
                Button(String(localized: "settings.logout.confirmAction"), role: .destructive) {
                    Task {
                        await viewModel.logout()
                    }
                }
                Button(String(localized: "settings.logout.cancel"), role: .cancel) {
                    // Dismiss
                }
            } message: {
                Text(String(localized: "settings.logout.confirmMessage"))
            }
            .task {
                await viewModel.loadProfile()
            }
            .sheet(isPresented: $viewModel.isShowingProfileEdit) {
                profileEditSheet
            }
            .onAppear {
                withAnimation(RFAnimation.springResponsive) {
                    isAppeared = true
                }
            }
        }
    }

    // MARK: - Profile Card

    private var profileCard: some View {
        RFCard(style: .glass, cornerRadius: RFCornerRadius.extraLarge) {
            HStack(spacing: RFSpacing.md) {
                RFAvatar(name: viewModel.displayName, size: .large, showRing: true)

                VStack(alignment: .leading, spacing: RFSpacing.xxs) {
                    if viewModel.isLoadingProfile {
                        ProgressView()
                    } else {
                        RFText(viewModel.displayName, style: .title)
                        RFText(viewModel.email, style: .caption)
                    }
                }

                Spacer()

                Image(systemName: "pencil")
                    .font(.caption)
                    .foregroundStyle(RFColors.fallbackTextTertiary)
            }
        }
        .onTapGesture {
            viewModel.showProfileEdit()
        }
    }

    private var profileEditSheet: some View {
        NavigationStack {
            Form {
                Section(String(localized: "settings.profile.displayName")) {
                    TextField(
                        String(localized: "settings.profile.displayNamePlaceholder"),
                        text: $viewModel.editingDisplayName
                    )
                }
            }
            .navigationTitle(String(localized: "settings.profile.editTitle"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button(String(localized: "settings.profile.cancel")) {
                        viewModel.isShowingProfileEdit = false
                    }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button(String(localized: "settings.profile.save")) {
                        Task {
                            await viewModel.saveProfileChanges()
                        }
                    }
                }
            }
        }
        .presentationDetents([.medium])
    }

    // MARK: - Security Card

    private var securityCard: some View {
        RFCard {
            VStack(spacing: RFSpacing.md) {
                settingsCardHeader(
                    icon: "faceid",
                    title: String(localized: "settings.security.title"),
                    color: .green
                )

                Toggle(isOn: Binding(
                    get: { viewModel.isBiometricEnabled },
                    set: { viewModel.updateBiometricEnabled($0) }
                )) {
                    RFText(String(localized: "settings.security.faceID"), style: .body)
                }
                .tint(RFColors.fallbackPrimary)
            }
        }
        .sensoryFeedback(.selection, trigger: viewModel.isBiometricEnabled)
    }

    // MARK: - Voice Settings Card

    private var voiceSettingsCard: some View {
        RFCard {
            VStack(spacing: RFSpacing.md) {
                settingsCardHeader(
                    icon: "speaker.wave.2.fill",
                    title: String(localized: "settings.section.voice"),
                    color: RFColors.info
                )

                VStack(alignment: .leading, spacing: RFSpacing.xs) {
                    HStack {
                        RFText(
                            String(localized: "settings.voice.speed"),
                            style: .body
                        )
                        Spacer()
                        RFText(viewModel.ttsSpeedText, style: .captionBold)
                    }
                    Slider(
                        value: Binding(
                            get: { viewModel.settings.ttsSpeed },
                            set: { viewModel.updateTTSSpeed($0) }
                        ),
                        in: 0.5...2.0,
                        step: 0.1
                    )
                    .tint(RFColors.fallbackPrimary)
                }

                Divider()

                settingsToggleRow(
                    title: String(localized: "settings.voice.autoPlay"),
                    isOn: Binding(
                        get: { viewModel.settings.ttsAutoPlay },
                        set: { viewModel.updateTTSAutoPlay($0) }
                    )
                )

                Divider()

                settingsPickerRow(
                    title: String(localized: "settings.voice.language")
                ) {
                    Picker("", selection: Binding(
                        get: { viewModel.settings.ttsLanguage },
                        set: { viewModel.updateTTSLanguage($0) }
                    )) {
                        ForEach(TTSLanguage.allCases, id: \.self) { language in
                            Text(language.localizedTitle).tag(language)
                        }
                    }
                    .pickerStyle(.menu)
                }
            }
        }
    }

    // MARK: - Notification Settings Card

    private var notificationSettingsCard: some View {
        RFCard {
            VStack(spacing: RFSpacing.md) {
                settingsCardHeader(
                    icon: "bell.fill",
                    title: String(localized: "settings.section.notifications"),
                    color: RFColors.warning
                )

                settingsToggleRow(
                    title: String(localized: "settings.notification.push"),
                    isOn: Binding(
                        get: { viewModel.settings.pushNotificationsEnabled },
                        set: { viewModel.updatePushNotifications($0) }
                    )
                )

                if viewModel.settings.pushNotificationsEnabled {
                    ForEach(NotificationType.allCases, id: \.self) { type in
                        Divider()

                        settingsToggleRow(
                            title: type.localizedTitle,
                            isOn: Binding(
                                get: {
                                    viewModel.settings.enabledNotificationTypes
                                        .contains(type)
                                },
                                set: { enabled in
                                    viewModel.updateNotificationType(
                                        type,
                                        enabled: enabled
                                    )
                                }
                            )
                        )
                    }
                }
            }
        }
        .sensoryFeedback(.selection, trigger: viewModel.settings.pushNotificationsEnabled)
    }

    // MARK: - Appearance Settings Card

    private var appearanceSettingsCard: some View {
        RFCard {
            VStack(spacing: RFSpacing.md) {
                settingsCardHeader(
                    icon: "paintbrush.fill",
                    title: String(localized: "settings.section.appearance"),
                    color: .purple
                )

                settingsPickerRow(
                    title: String(localized: "settings.appearance.mode")
                ) {
                    Picker("", selection: Binding(
                        get: { viewModel.settings.appearance },
                        set: { viewModel.updateAppearance($0) }
                    )) {
                        ForEach(AppAppearance.allCases, id: \.self) { mode in
                            Text(mode.localizedTitle).tag(mode)
                        }
                    }
                    .pickerStyle(.menu)
                }

                Divider()

                settingsPickerRow(
                    title: String(localized: "settings.appearance.fontSize")
                ) {
                    Picker("", selection: Binding(
                        get: { viewModel.settings.fontSize },
                        set: { viewModel.updateFontSize($0) }
                    )) {
                        ForEach(AppFontSize.allCases, id: \.self) { size in
                            Text(size.localizedTitle).tag(size)
                        }
                    }
                    .pickerStyle(.menu)
                }
            }
        }
    }

    // MARK: - App Info Card

    private var appInfoCard: some View {
        RFCard {
            HStack {
                settingsCardHeader(
                    icon: "info.circle.fill",
                    title: String(localized: "settings.version"),
                    color: RFColors.fallbackTextSecondary
                )
                Spacer()
                RFText(viewModel.appVersion, style: .caption)
            }
        }
    }

    // MARK: - Logout Card

    private var logoutCard: some View {
        RFButton(
            String(localized: "settings.logout"),
            style: .destructive,
            size: .medium
        ) {
            viewModel.showLogoutConfirmation()
        }
    }

    // MARK: - Reusable Card Components

    private func settingsCardHeader(
        icon: String,
        title: String,
        color: Color
    ) -> some View {
        HStack(spacing: RFSpacing.sm) {
            Image(systemName: icon)
                .font(.body)
                .foregroundStyle(color)

            RFText(title, style: .headline)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func settingsToggleRow(
        title: String,
        isOn: Binding<Bool>
    ) -> some View {
        Toggle(isOn: isOn) {
            RFText(title, style: .body)
        }
        .tint(RFColors.fallbackPrimary)
    }

    private func settingsPickerRow<PickerContent: View>(
        title: String,
        @ViewBuilder picker: () -> PickerContent
    ) -> some View {
        HStack {
            RFText(title, style: .body)
            Spacer()
            picker()
        }
    }
}

#Preview {
    let settingsRepo = SettingsRepositoryImpl()
    let userRepo = UserRepositoryImpl(networkClient: NetworkClient())
    let keychain = KeychainHelper()
    let authManager = AuthManager(keychain: keychain)
    let biometricManager = BiometricAuthManager()
    let viewModel = SettingsViewModel(
        loadSettingsUseCase: LoadSettingsUseCase(repository: settingsRepo),
        saveSettingsUseCase: SaveSettingsUseCase(repository: settingsRepo),
        loadProfileUseCase: LoadProfileUseCase(repository: userRepo),
        updateProfileUseCase: UpdateProfileUseCase(repository: userRepo),
        logoutUseCase: LogoutUseCase(authManager: authManager),
        authManager: authManager,
        biometricManager: biometricManager
    )
    SettingsView(viewModel: viewModel)
}
