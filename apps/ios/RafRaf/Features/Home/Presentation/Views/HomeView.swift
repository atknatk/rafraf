import Factory
import SwiftUI

/// Ana sayfa ekrani.
/// Kullanicinin projelerini ve son aktivitelerini goruntuledigü ekran.
/// Gradient arkaplan, hero karti ve hizli aksiyon kartlari ile modern dashboard.
struct HomeView: View {
    @State private var viewModel = HomeViewModel()
    @State private var isAppeared = false
    @State private var showProjectList = false
    @State private var projectListViewModel = Container.shared.projectListViewModel()

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
            .navigationDestination(isPresented: $showProjectList) {
                ProjectListView(
                    viewModel: projectListViewModel
                )
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

                RFEmptyStateView(
                    systemImage: "folder",
                    title: String(localized: "home.empty.title"),
                    message: String(localized: "home.empty.message"),
                    actionTitle: String(localized: "home.empty.action")
                ) {
                    showProjectList = true
                }
                .rfEntrance(isAppeared: isAppeared, delay: 0.25)
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
                            Color(light: Color(red: 0.72, green: 0.37, blue: 0.22),
                                  dark: Color(red: 0.68, green: 0.34, blue: 0.19)),
                            Color(light: Color(red: 0.62, green: 0.28, blue: 0.16),
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
            quickActionCard(
                icon: "folder.fill",
                title: String(localized: "home.action.projects"),
                gradient: RFColors.accentGradient,
                action: { showProjectList = true }
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
}

#Preview {
    HomeView()
}
