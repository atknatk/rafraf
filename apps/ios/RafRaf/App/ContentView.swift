import Factory
import SwiftUI

/// Ana kok gorunum.
/// Auth durumuna gore login ekrani veya tab bar gosterir.
struct ContentView: View {
    @Injected(\.authManager) private var authManager
    @State private var selectedTab: AppTab = .home

    var body: some View {
        Group {
            switch authManager.authState {
            case .unknown:
                RFLoadingView(
                    message: String(localized: "auth.checking")
                )
            case .authenticated:
                mainTabView
            case .unauthenticated:
                authView
            }
        }
        .task {
            await authManager.checkExistingAuth()
        }
    }

    // MARK: - Views

    @ViewBuilder
    private var mainTabView: some View {
        TabView(selection: $selectedTab) {
            HomeView()
                .tabItem {
                    Label(String(localized: "tab.home"), systemImage: "house.fill")
                }
                .tag(AppTab.home)

            ChatView(viewModel: Container.shared.chatViewModel())
                .tabItem {
                    Label(String(localized: "tab.chat"), systemImage: "message.fill")
                }
                .tag(AppTab.chat)

            SettingsView(viewModel: Container.shared.settingsViewModel())
                .tabItem {
                    Label(String(localized: "tab.settings"), systemImage: "gearshape.fill")
                }
                .tag(AppTab.settings)
        }
    }

    @ViewBuilder
    private var authView: some View {
        let viewModel = Container.shared.authViewModel()
        if viewModel.isShowingRegister {
            RFRegisterView(viewModel: viewModel)
        } else {
            RFLoginView(viewModel: viewModel)
        }
    }
}

/// Uygulama tab tipleri.
enum AppTab: String, Hashable, Sendable {
    case home
    case chat
    case settings
}

#Preview {
    ContentView()
}
