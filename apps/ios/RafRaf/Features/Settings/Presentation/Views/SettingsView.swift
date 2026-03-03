import SwiftUI

/// Ayarlar ana ekrani.
/// Profil, ses, bildirim, gorunum ve hesap ayarlarini bolumler halinde gosterir.
struct SettingsView: View {
    @State private var viewModel: SettingsViewModel

    init(viewModel: SettingsViewModel) {
        self._viewModel = State(initialValue: viewModel)
    }

    var body: some View {
        NavigationStack {
            List {
                profileSection
                voiceSettingsSection
                notificationSettingsSection
                appearanceSettingsSection
                appInfoSection
                logoutSection
            }
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
        }
    }

    // MARK: - Profile Section

    private var profileSection: some View {
        Section {
            HStack(spacing: RFSpacing.sm) {
                RFAvatar(name: viewModel.displayName, size: .medium)

                VStack(alignment: .leading, spacing: RFSpacing.xxs) {
                    RFText(viewModel.displayName, style: .bodyBold)
                    RFText(viewModel.email, style: .caption)
                }
            }
            .padding(.vertical, RFSpacing.xs)
        } header: {
            Text(String(localized: "settings.section.profile"))
        }
    }

    // MARK: - Voice Settings Section

    private var voiceSettingsSection: some View {
        Section {
            // TTS hizi
            VStack(alignment: .leading, spacing: RFSpacing.xs) {
                HStack {
                    RFSettingsRow(
                        icon: "speedometer",
                        iconColor: RFColors.info,
                        title: String(localized: "settings.voice.speed")
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

            // Auto-play
            RFSettingsToggleRow(
                icon: "play.circle",
                iconColor: RFColors.info,
                title: String(localized: "settings.voice.autoPlay"),
                isOn: Binding(
                    get: { viewModel.settings.ttsAutoPlay },
                    set: { viewModel.updateTTSAutoPlay($0) }
                )
            )

            // Dil secimi
            HStack {
                RFSettingsRow(
                    icon: "globe",
                    iconColor: RFColors.info,
                    title: String(localized: "settings.voice.language")
                )
                Spacer()
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
        } header: {
            Text(String(localized: "settings.section.voice"))
        }
    }

    // MARK: - Notification Settings Section

    private var notificationSettingsSection: some View {
        Section {
            // Push bildirimler
            RFSettingsToggleRow(
                icon: "bell",
                iconColor: RFColors.warning,
                title: String(localized: "settings.notification.push"),
                isOn: Binding(
                    get: { viewModel.settings.pushNotificationsEnabled },
                    set: { viewModel.updatePushNotifications($0) }
                )
            )

            // Bildirim tipleri
            if viewModel.settings.pushNotificationsEnabled {
                ForEach(NotificationType.allCases, id: \.self) { type in
                    RFSettingsToggleRow(
                        icon: notificationTypeIcon(type),
                        iconColor: RFColors.warning,
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
        } header: {
            Text(String(localized: "settings.section.notifications"))
        }
    }

    // MARK: - Appearance Settings Section

    private var appearanceSettingsSection: some View {
        Section {
            // Gorunum modu
            HStack {
                RFSettingsRow(
                    icon: "paintbrush",
                    iconColor: .purple,
                    title: String(localized: "settings.appearance.mode")
                )
                Spacer()
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

            // Font boyutu
            HStack {
                RFSettingsRow(
                    icon: "textformat.size",
                    iconColor: .purple,
                    title: String(localized: "settings.appearance.fontSize")
                )
                Spacer()
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
        } header: {
            Text(String(localized: "settings.section.appearance"))
        }
    }

    // MARK: - App Info Section

    private var appInfoSection: some View {
        Section {
            HStack {
                RFSettingsRow(
                    icon: "info.circle",
                    iconColor: RFColors.fallbackTextSecondary,
                    title: String(localized: "settings.version")
                )
                Spacer()
                RFText(viewModel.appVersion, style: .caption)
            }
        } header: {
            Text(String(localized: "settings.section.app"))
        }
    }

    // MARK: - Logout Section

    private var logoutSection: some View {
        Section {
            RFButton(
                String(localized: "settings.logout"),
                style: .destructive,
                size: .medium
            ) {
                viewModel.showLogoutConfirmation()
            }
        }
    }

    // MARK: - Helpers

    private func notificationTypeIcon(_ type: NotificationType) -> String {
        switch type {
        case .taskUpdates: return "checkmark.circle"
        case .approvalRequests: return "hand.thumbsup"
        case .systemAlerts: return "exclamationmark.triangle"
        }
    }
}

#Preview {
    let repository = SettingsRepositoryImpl()
    let viewModel = SettingsViewModel(
        loadSettingsUseCase: LoadSettingsUseCase(repository: repository),
        saveSettingsUseCase: SaveSettingsUseCase(repository: repository)
    )
    SettingsView(viewModel: viewModel)
}
