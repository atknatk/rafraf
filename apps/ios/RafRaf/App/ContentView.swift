import Factory
import SwiftUI

/// Ana kok gorunum.
/// Auth durumuna gore login ekrani veya tab bar gosterir.
/// Glass material tab bar ve auth gecis animasyonu ile premium gorunum.
struct ContentView: View {
    @Injected(\.authManager) private var authManager
    @State private var selectedTab: AppTab = .home
    @State private var chatSessionManager = Container.shared.chatSessionManager()
    @State private var agentListViewModel = Container.shared.agentListViewModel()
    @State private var settingsViewModel = Container.shared.settingsViewModel()
    @State private var authViewModel = Container.shared.authViewModel()
    @State private var notificationCenterViewModel = Container.shared.notificationCenterViewModel()
    @State private var isShowingNotifications = false
    /// V1.5: Backend-originated approval question presenter.
    /// Singleton — DI'dan ayni instance gelir; root view `.sheet(item:)` ile
    /// observe eder, WebSocket handler queue'ya iter.
    @State private var approvalCoordinator = Container.shared.approvalCoordinator()
    private let webSocketManager = Container.shared.webSocketConnectionManager()
    private let subagentRepository = Container.shared.subagentRepository()
    private let approvalQuestionMessageHandler = Container.shared.approvalQuestionMessageHandler()
    /// V1.x SHIP BLOCKER fix — backend `ack` envelope handler.
    /// Singleton DI ile `ApprovalRepositoryImpl` ile ayni inbox'a baglanir.
    private let approvalDeliveryAckMessageHandler = Container.shared.approvalDeliveryAckMessageHandler()
    /// V1.x SLIM (Item 11) — Claude subprocess supervisor handler bundle.
    /// 6 inbound `event.claude.process.*` envelope'i app start'inda
    /// `WebSocketMessageRouter`'a kaydedilir.
    private let claudeProcessMessageHandlers = Container.shared.claudeProcessMessageHandlers()

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
        // V1.5: Backend-originated approval question sheet — root view'a baglandi
        // ki herhangi bir tab aktifken (chat / agents / settings) sheet ustte
        // gosterilebilsin. ApprovalCoordinator queue tek instance.
        .sheet(item: $approvalCoordinator.activeRequest) { request in
            RFApprovalSheet(request: request) { choice in
                Task {
                    await approvalCoordinator.handleDecision(choice)
                }
            }
        }
        .task {
            // Reconnect callback — kacirilmis mesajlari fetch et
            webSocketManager.onReconnect = { [chatSessionManager] in
                await chatSessionManager.fetchMissedMessagesForAll()
            }

            // Claude Agent Teams subagent handler'larini WebSocket router'a bagla.
            // Doc 10 §6.3.3 — T1.7. Acilis sirasinda bir kez kayit yeterli.
            await registerSubagentHandlers()

            // V1.5: Backend-originated approval question handler'ini router'a bagla.
            // `question` envelope decode edildiginde coordinator queue'ya itilir.
            await registerApprovalQuestionHandler()

            // V1.x SHIP BLOCKER fix: backend `ack` envelope handler'ini router'a bagla.
            // ApprovalRepositoryImpl ile ayni singleton inbox'i paylasir; ack
            // geldiginde bekleyen `awaitAck` continuation'i cozulur.
            await registerApprovalDeliveryAckHandler()

            // V1.x SLIM (Item 11): Claude subprocess supervisor handler'lari.
            // Bridge'den gelen 6 `event.claude.process.*` envelope'i tek bir DI
            // bundle ile router'a baglanir.
            await registerClaudeProcessHandlers()

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
                    // V1.5 reviewer M2 fix: coordinator is a Factory
                    // singleton — without explicit reset, a residual
                    // approval sheet from the prior session would
                    // persist for the next user. Drop the active
                    // request + queue on auth transition.
                    await approvalCoordinator.reset()
                }
            }
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

    // MARK: - Subagent Handlers

    /// Doc 10 §6.3.3 — `subagent.spawned` / `subagent.progress` /
    /// `subagent.completed` mesajlarini SubagentRepositoryImpl'e tasiyan
    /// handler'lari WebSocketMessageRouter'a kaydeder. T1.6 sonrasi
    /// router'da kalan TODO'lar bu cagri ile gercek handler'a baglanir.
    private func registerSubagentHandlers() async {
        await webSocketManager.registerHandler(
            type: WebSocketMessageType.subagentSpawned.rawValue,
            handler: SubagentSpawnedHandler(repository: subagentRepository)
        )
        await webSocketManager.registerHandler(
            type: WebSocketMessageType.subagentProgress.rawValue,
            handler: SubagentProgressHandler(repository: subagentRepository)
        )
        await webSocketManager.registerHandler(
            type: WebSocketMessageType.subagentCompleted.rawValue,
            handler: SubagentCompletedHandler(repository: subagentRepository)
        )
    }

    /// V1.5: Backend `question` envelope'ini ApprovalCoordinator'a tasiyan
    /// handler kaydi.
    private func registerApprovalQuestionHandler() async {
        await webSocketManager.registerHandler(
            type: WebSocketMessageType.question.rawValue,
            handler: approvalQuestionMessageHandler
        )
    }

    /// V1.x SHIP BLOCKER fix — backend `ack` envelope'ini
    /// `ApprovalDeliveryAckInbox`'a tasiyan handler kaydi.
    /// `type: "ack"` raw string — kontrat: shared/api-contracts/ws/ack-messages.json.
    private func registerApprovalDeliveryAckHandler() async {
        await webSocketManager.registerHandler(
            type: "ack",
            handler: approvalDeliveryAckMessageHandler
        )
    }

    /// V1.x SLIM (Item 11) — Claude subprocess supervisor envelope handler'lari.
    /// Spec §4: spawned / healthcheck / stalled / crashed / recovered / diagnosed.
    private func registerClaudeProcessHandlers() async {
        await webSocketManager.registerHandler(
            type: WebSocketMessageType.claudeProcessSpawned.rawValue,
            handler: claudeProcessMessageHandlers.spawned
        )
        await webSocketManager.registerHandler(
            type: WebSocketMessageType.claudeProcessHealthcheck.rawValue,
            handler: claudeProcessMessageHandlers.healthcheck
        )
        await webSocketManager.registerHandler(
            type: WebSocketMessageType.claudeProcessStalled.rawValue,
            handler: claudeProcessMessageHandlers.stalled
        )
        await webSocketManager.registerHandler(
            type: WebSocketMessageType.claudeProcessCrashed.rawValue,
            handler: claudeProcessMessageHandlers.crashed
        )
        await webSocketManager.registerHandler(
            type: WebSocketMessageType.claudeProcessRecovered.rawValue,
            handler: claudeProcessMessageHandlers.recovered
        )
        await webSocketManager.registerHandler(
            type: WebSocketMessageType.claudeProcessDiagnosed.rawValue,
            handler: claudeProcessMessageHandlers.diagnosed
        )
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
    case home
    case chat
    case agents
    case settings
}

#Preview {
    ContentView()
}
