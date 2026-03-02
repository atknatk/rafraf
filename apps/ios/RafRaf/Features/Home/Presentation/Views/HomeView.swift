import SwiftUI

/// Ana sayfa ekrani.
/// Kullanicinin projelerini ve son aktivitelerini goruntuledigü ekran.
struct HomeView: View {
    @State private var viewModel = HomeViewModel()

    var body: some View {
        NavigationStack {
            Group {
                if viewModel.isLoading {
                    RFLoadingView(
                        message: String(localized: "home.loading")
                    )
                } else {
                    contentView
                }
            }
            .navigationTitle(String(localized: "home.title"))
        }
    }

    @ViewBuilder
    private var contentView: some View {
        ScrollView {
            VStack(spacing: RFSpacing.md) {
                // Hosgeldin karti
                RFCard {
                    VStack(alignment: .leading, spacing: RFSpacing.xs) {
                        RFText(
                            String(localized: "home.welcome.title"),
                            style: .title
                        )
                        RFText(
                            String(localized: "home.welcome.subtitle"),
                            style: .body,
                            color: RFColors.fallbackTextSecondary
                        )
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }

                // Bos durum (scaffold)
                RFEmptyStateView(
                    systemImage: "folder",
                    title: String(localized: "home.empty.title"),
                    message: String(localized: "home.empty.message"),
                    actionTitle: String(localized: "home.empty.action")
                ) {
                    // Yeni proje olustur
                }
            }
            .padding(RFSpacing.md)
        }
    }
}

#Preview {
    HomeView()
}
