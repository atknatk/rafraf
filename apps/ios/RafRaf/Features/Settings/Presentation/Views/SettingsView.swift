import SwiftUI

/// Ayarlar ekrani.
/// Kullanici profili, uygulama ayarlari ve cikis islemi.
struct SettingsView: View {
    @State private var viewModel = SettingsViewModel()

    var body: some View {
        NavigationStack {
            List {
                // Profil bolumu
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

                // Uygulama ayarlari
                Section {
                    HStack {
                        RFText(
                            String(localized: "settings.version"),
                            style: .body
                        )
                        Spacer()
                        RFText(
                            viewModel.appVersion,
                            style: .caption
                        )
                    }
                } header: {
                    Text(String(localized: "settings.section.app"))
                }

                // Cikis
                Section {
                    RFButton(
                        String(localized: "settings.logout"),
                        style: .destructive,
                        size: .medium
                    ) {
                        Task {
                            await viewModel.logout()
                        }
                    }
                }
            }
            .navigationTitle(String(localized: "settings.title"))
        }
    }
}

#Preview {
    SettingsView()
}
