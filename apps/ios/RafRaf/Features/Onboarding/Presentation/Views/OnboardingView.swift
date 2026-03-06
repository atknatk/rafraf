import SwiftUI

// MARK: - OnboardingPage Model

/// Onboarding sayfasi verisi.
struct OnboardingPage {
    let icon: String
    let titleKey: String
    let subtitleKey: String
    let color: Color
}

// MARK: - OnboardingView

/// Ilk kullanim karsilama ekrani.
/// TabView tabanli 4 sayfali onboarding akisi.
struct OnboardingView: View {
    @State private var currentPage = 0
    var onComplete: () -> Void

    private let pages: [OnboardingPage] = [
        OnboardingPage(
            icon: "brain.head.profile",
            titleKey: "onboarding.page1.title",
            subtitleKey: "onboarding.page1.subtitle",
            color: .blue
        ),
        OnboardingPage(
            icon: "server.rack",
            titleKey: "onboarding.page2.title",
            subtitleKey: "onboarding.page2.subtitle",
            color: .purple
        ),
        OnboardingPage(
            icon: "chart.bar.xaxis",
            titleKey: "onboarding.page3.title",
            subtitleKey: "onboarding.page3.subtitle",
            color: .green
        ),
        OnboardingPage(
            icon: "checkmark.circle.fill",
            titleKey: "onboarding.page4.title",
            subtitleKey: "onboarding.page4.subtitle",
            color: .orange
        ),
    ]

    var body: some View {
        ZStack {
            Color(.systemBackground)
                .ignoresSafeArea()

            VStack(spacing: 0) {
                // Page content
                TabView(selection: $currentPage) {
                    ForEach(Array(pages.enumerated()), id: \.offset) { index, page in
                        OnboardingPageView(page: page)
                            .tag(index)
                    }
                }
                .tabViewStyle(.page(indexDisplayMode: .never))
                .animation(.spring(response: 0.5, dampingFraction: 0.8), value: currentPage)

                // Bottom controls
                VStack(spacing: 24) {
                    // Page indicator dots
                    HStack(spacing: 8) {
                        ForEach(0..<pages.count, id: \.self) { index in
                            Circle()
                                .fill(index == currentPage ? Color.accentColor : Color(.systemGray4))
                                .frame(
                                    width: index == currentPage ? 10 : 8,
                                    height: index == currentPage ? 10 : 8
                                )
                                .animation(.spring(response: 0.3, dampingFraction: 0.7), value: currentPage)
                        }
                    }

                    // Action button
                    if currentPage < pages.count - 1 {
                        RFButton(
                            String(localized: "onboarding.next"),
                            style: .primary,
                            size: .large
                        ) {
                            withAnimation(.spring(response: 0.5, dampingFraction: 0.8)) {
                                currentPage += 1
                            }
                        }
                        .padding(.horizontal, 32)
                    } else {
                        RFButton(
                            String(localized: "onboarding.getStarted"),
                            style: .primary,
                            size: .large,
                            systemImage: "arrow.right.circle.fill"
                        ) {
                            OnboardingService.shared.completeOnboarding()
                            onComplete()
                        }
                        .padding(.horizontal, 32)
                    }
                }
                .padding(.bottom, 48)
                .padding(.top, 24)
            }
        }
    }
}

// MARK: - OnboardingPageView

/// Tek onboarding sayfa icerigi.
private struct OnboardingPageView: View {
    let page: OnboardingPage

    var body: some View {
        VStack(spacing: 32) {
            Spacer()

            // Icon
            ZStack {
                Circle()
                    .fill(page.color.opacity(0.12))
                    .frame(width: 160, height: 160)

                Image(systemName: page.icon)
                    .font(.system(size: 72, weight: .medium))
                    .foregroundStyle(page.color)
            }

            // Text content
            VStack(spacing: 16) {
                Text(String(localized: String.LocalizationValue(page.titleKey)))
                    .font(.title.bold())
                    .multilineTextAlignment(.center)
                    .foregroundStyle(.primary)

                Text(String(localized: String.LocalizationValue(page.subtitleKey)))
                    .font(.body)
                    .multilineTextAlignment(.center)
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, 32)
            }

            Spacer()
            Spacer()
        }
        .padding(.horizontal, 16)
    }
}

// MARK: - Preview

#Preview("Onboarding") {
    OnboardingView {
        // Preview completion
    }
}

#Preview("Page 1") {
    OnboardingPageView(
        page: OnboardingPage(
            icon: "brain.head.profile",
            titleKey: "onboarding.page1.title",
            subtitleKey: "onboarding.page1.subtitle",
            color: .blue
        )
    )
}
