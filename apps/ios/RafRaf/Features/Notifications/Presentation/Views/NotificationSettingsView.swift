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
                pulseSection
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

    // MARK: - Pulse Section

    private var pulseSection: some View {
        Section {
            if viewModel.isPulseLoading {
                HStack {
                    ProgressView()
                        .padding(.trailing, RFSpacing.xs)
                    RFText(
                        String(localized: "pulse.loading"),
                        style: .body
                    )
                }
            } else if let pulse = viewModel.pulseReport {
                PulseCard(pulse: pulse)
            } else {
                RFText(
                    String(localized: "pulse.notAvailable"),
                    style: .caption
                )
                .foregroundStyle(.secondary)
            }
        } header: {
            Text(String(localized: "pulse.section.title"))
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

// MARK: - PulseCard

/// Gunluk AI proje ozeti karti.
private struct PulseCard: View {
    let pulse: PulseReportDTO

    var body: some View {
        VStack(alignment: .leading, spacing: RFSpacing.sm) {
            RFText(pulse.summaryText, style: .body)

            if !pulse.completedItems.isEmpty {
                itemList(
                    title: String(localized: "pulse.completed"),
                    items: pulse.completedItems,
                    icon: "checkmark.circle.fill",
                    color: RFColors.success
                )
            }

            if !pulse.inProgressItems.isEmpty {
                itemList(
                    title: String(localized: "pulse.inProgress"),
                    items: pulse.inProgressItems,
                    icon: "clock.fill",
                    color: RFColors.warning
                )
            }

            if !pulse.risks.isEmpty {
                itemList(
                    title: String(localized: "pulse.risks"),
                    items: pulse.risks,
                    icon: "exclamationmark.triangle.fill",
                    color: RFColors.error
                )
            }

            if !pulse.suggestions.isEmpty {
                itemList(
                    title: String(localized: "pulse.suggestions"),
                    items: pulse.suggestions,
                    icon: "lightbulb.fill",
                    color: RFColors.info
                )
            }

            RFText(
                String(localized: "pulse.generatedAt") + " " + pulse.reportDate,
                style: .caption
            )
            .foregroundStyle(.secondary)
        }
        .padding(.vertical, RFSpacing.xs)
    }

    private func itemList(
        title: String,
        items: [String],
        icon: String,
        color: Color
    ) -> some View {
        VStack(alignment: .leading, spacing: RFSpacing.xxs) {
            HStack(spacing: RFSpacing.xs) {
                Image(systemName: icon)
                    .foregroundStyle(color)
                    .font(.caption)
                RFText(title, style: .caption)
                    .foregroundStyle(color)
            }
            ForEach(items, id: \.self) { item in
                HStack(alignment: .top, spacing: RFSpacing.xs) {
                    Text("•")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    RFText(item, style: .caption)
                        .foregroundStyle(.secondary)
                }
                .padding(.leading, RFSpacing.sm)
            }
        }
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
