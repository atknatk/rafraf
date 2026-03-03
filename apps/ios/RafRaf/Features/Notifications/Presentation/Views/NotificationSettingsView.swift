import SwiftUI

/// Bildirim ayarlari ekrani.
/// Push bildirim izni, kategori tercihleri ve bildirim test ayarlarini gosterir.
struct NotificationSettingsView: View {
    @State private var viewModel: NotificationSettingsViewModel

    init(viewModel: NotificationSettingsViewModel) {
        self._viewModel = State(initialValue: viewModel)
    }

    var body: some View {
        NavigationStack {
            List {
                permissionSection
                if viewModel.permissionStatus == .authorized {
                    categorySection
                }
            }
            .navigationTitle(String(localized: "notification.settings.title"))
            .task {
                await viewModel.onAppear()
            }
            .overlay {
                if viewModel.isLoading {
                    RFLoadingView(
                        message: String(localized: "notification.settings.loading")
                    )
                }
            }
        }
    }

    // MARK: - Permission Section

    private var permissionSection: some View {
        Section {
            switch viewModel.permissionStatus {
            case .authorized:
                HStack {
                    RFSettingsRow(
                        icon: "bell.badge.fill",
                        iconColor: RFColors.success,
                        title: String(localized: "notification.permission.authorized")
                    )
                    Spacer()
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundStyle(RFColors.success)
                }
            case .denied:
                VStack(alignment: .leading, spacing: RFSpacing.sm) {
                    RFSettingsRow(
                        icon: "bell.slash.fill",
                        iconColor: RFColors.error,
                        title: String(localized: "notification.permission.denied")
                    )
                    RFText(
                        String(localized: "notification.permission.deniedDescription"),
                        style: .caption
                    )
                    RFButton(
                        String(localized: "notification.permission.openSettings"),
                        style: .outline,
                        size: .small
                    ) {
                        openSystemSettings()
                    }
                }
            case .unknown, .provisional:
                VStack(alignment: .leading, spacing: RFSpacing.sm) {
                    RFSettingsRow(
                        icon: "bell",
                        iconColor: RFColors.warning,
                        title: String(localized: "notification.permission.notDetermined")
                    )
                    RFButton(
                        String(localized: "notification.permission.enable"),
                        style: .primary,
                        size: .medium
                    ) {
                        Task {
                            await viewModel.requestPermission()
                        }
                    }
                }
            }
        } header: {
            Text(String(localized: "notification.section.permission"))
        }
    }

    // MARK: - Category Section

    private var categorySection: some View {
        Section {
            ForEach(NotificationCategory.allCases, id: \.self) { category in
                RFSettingsToggleRow(
                    icon: category.iconName,
                    iconColor: categoryColor(category),
                    title: category.localizedTitle,
                    isOn: Binding(
                        get: { viewModel.isCategoryEnabled(category) },
                        set: { enabled in
                            Task {
                                await viewModel.updateCategory(
                                    category,
                                    enabled: enabled
                                )
                            }
                        }
                    )
                )
            }
        } header: {
            Text(String(localized: "notification.section.categories"))
        } footer: {
            RFText(
                String(localized: "notification.section.categoriesFooter"),
                style: .caption
            )
        }
    }

    // MARK: - Helpers

    private func categoryColor(_ category: NotificationCategory) -> Color {
        switch category {
        case .taskComplete: return RFColors.success
        case .approvalNeeded: return RFColors.warning
        case .error: return RFColors.error
        case .info: return RFColors.info
        }
    }

    private func openSystemSettings() {
        guard let url = URL(string: UIApplication.openSettingsURLString) else {
            return
        }
        UIApplication.shared.open(url)
    }
}

#Preview {
    let repository = NotificationRepositoryImpl(
        networkClient: NetworkClient()
    )
    let manager = PushNotificationManager()
    let viewModel = NotificationSettingsViewModel(
        registerDeviceTokenUseCase: RegisterDeviceTokenUseCase(
            repository: repository
        ),
        notificationManager: manager,
        repository: repository
    )
    NotificationSettingsView(viewModel: viewModel)
}
