import Factory
import SwiftUI

/// Ana kok gorunum.
/// Auth durumuna gore login ekrani veya tab bar gosterir.
/// Glass material tab bar ve auth gecis animasyonu ile premium gorunum.
struct ContentView: View {
    @Injected(\.authManager) private var authManager
    @State private var selectedTab: AppTab = .projects
    @State private var projectListViewModel = Container.shared.projectListViewModel()
    @State private var chatSessionManager = Container.shared.chatSessionManager()
    @State private var agentListViewModel = Container.shared.agentListViewModel()
    @State private var settingsViewModel = Container.shared.settingsViewModel()
    @State private var authViewModel = Container.shared.authViewModel()
    @State private var notificationCenterViewModel = Container.shared.notificationCenterViewModel()
    @State private var isShowingNotifications = false
    private let webSocketManager = Container.shared.webSocketConnectionManager()

    init() {
        configureTabBarAppearance()
    }

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
        .animation(RFAnimation.springGentle, value: authManager.authState)
        .task {
            // Reconnect callback — kacirilmis mesajlari fetch et
            webSocketManager.onReconnect = { [chatSessionManager] in
                await chatSessionManager.fetchMissedMessagesForAll()
            }

            await authManager.checkExistingAuth()
            // Auth basarili ise hemen WebSocket bagla
            if authManager.authState == .authenticated {
                await webSocketManager.connect()
            }
        }
        .onChange(of: authManager.authState) { _, newState in
            Task {
                if newState == .authenticated {
                    await webSocketManager.connect()
                } else if newState == .unauthenticated {
                    await webSocketManager.disconnect()
                }
            }
        }
    }

    // MARK: - Views

    @ViewBuilder
    private var mainTabView: some View {
        TabView(selection: $selectedTab) {
            ProjectListView(viewModel: projectListViewModel)
                .tabItem {
                    Label(String(localized: "tab.projects"), systemImage: "folder.fill")
                }
                .tag(AppTab.projects)

            ChatView(sessionManager: chatSessionManager)
                .tabItem {
                    Label(String(localized: "tab.chat"), systemImage: "message.fill")
                }
                .tag(AppTab.chat)

            AgentListView(viewModel: agentListViewModel)
                .tabItem {
                    Label(String(localized: "tab.agents"), systemImage: "desktopcomputer")
                }
                .tag(AppTab.agents)

            SettingsView(viewModel: settingsViewModel)
                .tabItem {
                    Label(String(localized: "tab.settings"), systemImage: "gearshape.fill")
                }
                .tag(AppTab.settings)
        }
        .tint(RFColors.fallbackPrimary)
        .sensoryFeedback(.selection, trigger: selectedTab)
        .sheet(isPresented: $isShowingNotifications) {
            NotificationCenterView(viewModel: notificationCenterViewModel)
        }
    }

    @ViewBuilder
    private var authView: some View {
        Group {
            if authViewModel.isShowingRegister {
                RFRegisterView(viewModel: authViewModel)
                    .transition(RFTransition.slideForward)
            } else {
                RFLoginView(viewModel: authViewModel)
                    .transition(RFTransition.slideBack)
            }
        }
        .animation(RFAnimation.springResponsive, value: authViewModel.isShowingRegister)
    }

    // MARK: - Tab Bar Configuration

    private func configureTabBarAppearance() {
        let appearance = UITabBarAppearance()
        appearance.configureWithDefaultBackground()
        appearance.backgroundEffect = UIBlurEffect(style: .systemUltraThinMaterial)
        UITabBar.appearance().standardAppearance = appearance
        UITabBar.appearance().scrollEdgeAppearance = appearance
    }
}

/// Uygulama tab tipleri.
enum AppTab: String, Hashable, Sendable {
    case projects
    case chat
    case agents
    case settings
}

#Preview {
    ContentView()
}
