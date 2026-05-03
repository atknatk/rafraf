import Factory
import SwiftUI

/// Ana sayfa ekrani.
/// Kullanicinin projelerini ve son aktivitelerini goruntuledigü ekran.
/// Gradient arkaplan, hero karti ve hizli aksiyon kartlari ile modern dashboard.
///
/// T1.8 ile birlikte session listesindeki baslik alani Claude tarafindan
/// uretilen `ai-title` event'i geldikce canli olarak guncellenir
/// (`session.title` WebSocket mesaji → `HomeViewModel.applyTitleUpdate(_:)`).
struct HomeView: View {
    @State private var viewModel: HomeViewModel
    @State private var isAppeared = false

    @Injected(\.webSocketConnectionManager) private var webSocketManager
    @Injected(\.sessionTitleMessageHandler) private var sessionTitleMessageHandler

    /// Production init — DI tarafindan view model enjekte edilir.
    init() {
        let container = Container.shared
        _viewModel = State(initialValue: container.homeViewModel())
    }

    /// Test/Preview init — hazir bir view model ile renderlanir.
    init(viewModel: HomeViewModel) {
        _viewModel = State(initialValue: viewModel)
    }

    var body: some View {
        NavigationStack {
            ZStack {
                backgroundGradient

                Group {
                    if viewModel.isLoading {
                        HomeSkeletonView()
                    } else {
                        contentView
                    }
                }
            }
            .toolbar(.hidden, for: .navigationBar)
            .task {
                await registerSessionTitleHandler()
                await viewModel.loadData()
            }
        }
    }

    // MARK: - Background

    private var backgroundGradient: some View {
        LinearGradient(
            colors: [
                RFColors.heroGradientStart,
                RFColors.heroGradientEnd,
                RFColors.fallbackBackground
            ],
            startPoint: .top,
            endPoint: .bottom
        )
        .ignoresSafeArea()
    }

    // MARK: - Content

    @ViewBuilder
    private var contentView: some View {
        ScrollView {
            VStack(spacing: RFSpacing.lg) {
                heroSection
                    .rfEntrance(isAppeared: isAppeared, delay: 0.05)

                quickActionsSection
                    .rfEntrance(isAppeared: isAppeared, delay: 0.15)

                if let lastChat = viewModel.lastChat {
                    lastChatSection(message: lastChat)
                        .rfEntrance(isAppeared: isAppeared, delay: 0.20)
                }

                if viewModel.sessions.isEmpty {
                    RFEmptyStateView(
                        systemImage: "folder",
                        title: String(localized: "home.empty.title"),
                        message: String(localized: "home.empty.message"),
                        actionTitle: nil,
                        action: nil
                    )
                    .rfEntrance(isAppeared: isAppeared, delay: 0.25)
                } else {
                    sessionsSection
                        .rfEntrance(isAppeared: isAppeared, delay: 0.25)
                }
            }
            .padding(.horizontal, RFSpacing.md)
            .padding(.top, RFSpacing.xl)
        }
        .contentMargins(.bottom, RFSpacing.xxxl)
        .onAppear {
            withAnimation(RFAnimation.springResponsive) {
                isAppeared = true
            }
        }
    }

    // MARK: - Last Chat Preview

    private func lastChatSection(message: ChatMessage) -> some View {
        VStack(alignment: .leading, spacing: RFSpacing.sm) {
            RFText(
                String(localized: "home.lastChat.title"),
                style: .headline,
                color: .white
            )

            RFCard(style: .standard) {
                VStack(alignment: .leading, spacing: RFSpacing.xs) {
                    HStack(spacing: RFSpacing.xs) {
                        Image(systemName: lastChatIcon(for: message.sender))
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(RFColors.fallbackPrimary)
                        RFText(
                            lastChatRoleLabel(for: message.sender),
                            style: .captionBold,
                            color: RFColors.fallbackTextSecondary
                        )
                        Spacer()
                        RFText(
                            relativeTimestamp(message.timestamp),
                            style: .caption,
                            color: RFColors.fallbackTextTertiary
                        )
                    }

                    RFText(
                        lastChatPreview(message.content),
                        style: .body,
                        color: RFColors.fallbackTextPrimary
                    )
                    .lineLimit(3)
                    .multilineTextAlignment(.leading)
                }
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel(
            String(
                format: String(localized: "home.lastChat.a11y"),
                lastChatRoleLabel(for: message.sender),
                lastChatPreview(message.content)
            )
        )
    }

    private func lastChatIcon(for sender: MessageSender) -> String {
        switch sender {
        case .user: return "person.fill"
        case .assistant: return "sparkles"
        case .system: return "info.circle"
        }
    }

    private func lastChatRoleLabel(for sender: MessageSender) -> String {
        switch sender {
        case .user: return String(localized: "home.lastChat.role.user")
        case .assistant: return String(localized: "home.lastChat.role.assistant")
        case .system: return String(localized: "home.lastChat.role.system")
        }
    }

    private func lastChatPreview(_ content: String) -> String {
        let trimmed = content.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.count <= 240 {
            return trimmed
        }
        return String(trimmed.prefix(240)) + "…"
    }

    private func relativeTimestamp(_ date: Date) -> String {
        let formatter = RelativeDateTimeFormatter()
        formatter.unitsStyle = .abbreviated
        return formatter.localizedString(for: date, relativeTo: Date())
    }

    // MARK: - Hero Section

    private var heroSection: some View {
        HStack(alignment: .top) {
            VStack(alignment: .leading, spacing: RFSpacing.xxs) {
                RFText(
                    String(localized: "home.welcome.title"),
                    style: .largeTitle,
                    color: .white
                )
                RFText(
                    String(localized: "home.welcome.subtitle"),
                    style: .body,
                    color: .white.opacity(0.7)
                )
            }

            Spacer()

            RFAvatar(name: "User", size: .large, showRing: true)
        }
        .padding(RFSpacing.lg)
        .background {
            RoundedRectangle(cornerRadius: RFCornerRadius.extraLarge)
                .fill(
                    LinearGradient(
                        colors: [
                            Color.rfAdaptive(light: Color(red: 0.72, green: 0.37, blue: 0.22),
                                  dark: Color(red: 0.68, green: 0.34, blue: 0.19)),
                            Color.rfAdaptive(light: Color(red: 0.62, green: 0.28, blue: 0.16),
                                  dark: Color(red: 0.55, green: 0.26, blue: 0.14))
                        ],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )
        }
        .clipShape(RoundedRectangle(cornerRadius: RFCornerRadius.extraLarge))
        .rfElevation(.medium)
    }

    // MARK: - Quick Actions

    private var quickActionsSection: some View {
        HStack(spacing: RFSpacing.sm) {
            quickActionCard(
                icon: "message.fill",
                title: String(localized: "home.action.chat"),
                gradient: RFColors.brandGradient
            )
        }
    }

    private func quickActionCard(
        icon: String,
        title: String,
        gradient: LinearGradient,
        action: @escaping () -> Void = {}
    ) -> some View {
        RFCard(style: .interactive, onTap: action) {
            HStack(spacing: RFSpacing.sm) {
                Image(systemName: icon)
                    .font(.title3)
                    .foregroundStyle(.white)
                    .symbolEffect(.pulse, options: .nonRepeating)
                    .frame(width: 40, height: 40)
                    .background(gradient)
                    .clipShape(RoundedRectangle(cornerRadius: RFCornerRadius.medium))

                RFText(title, style: .headline)

                Spacer()

                Image(systemName: "chevron.right")
                    .font(.caption)
                    .foregroundStyle(RFColors.fallbackTextTertiary)
            }
        }
    }

    // MARK: - Sessions Section

    private var sessionsSection: some View {
        VStack(alignment: .leading, spacing: RFSpacing.sm) {
            RFText(
                String(localized: "home.sessions.title"),
                style: .headline,
                color: .white
            )

            VStack(spacing: RFSpacing.sm) {
                ForEach(viewModel.sessions) { session in
                    HomeSessionRow(session: session)
                        .animation(RFAnimation.springResponsive, value: session.aiTitle)
                }
            }
        }
    }

    // MARK: - WebSocket handler registration

    private func registerSessionTitleHandler() async {
        await webSocketManager.registerHandler(
            type: WebSocketMessageType.sessionTitle.rawValue,
            handler: sessionTitleMessageHandler
        )
    }
}

#Preview("with sessions") {
    let viewModel = HomeViewModel()
    viewModel.seedSessions([
        HomeSession(
            id: "00000000-0000-0000-0000-000000000001",
            title: "Backend testleri",
            aiTitle: "Backend test sonuclarinin incelenmesi"
        ),
        HomeSession(
            id: "00000000-0000-0000-0000-000000000002",
            title: "Yeni session",
            aiTitle: nil
        )
    ])
    return HomeView(viewModel: viewModel)
}

#Preview("empty") {
    HomeView(viewModel: HomeViewModel())
}
