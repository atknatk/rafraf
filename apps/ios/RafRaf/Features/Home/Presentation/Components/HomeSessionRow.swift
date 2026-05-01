import SwiftUI

/// Home session listesinde bir oturumu temsil eden satir.
///
/// `aiTitle` mevcut oldugunda bu baslik buyuk fontla one cikar ve "AI"
/// rozet gosterilir; raw `title` daha kucuk ikincil metin olarak yer alir.
/// AI baslik henuz uretilmemisse placeholder gosterilir.
///
/// Doc 10 §6.3.4. T1.8.
struct HomeSessionRow: View {
    let session: HomeSession

    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        RFCard(style: .standard) {
            HStack(alignment: .top, spacing: RFSpacing.sm) {
                Image(systemName: "bubble.left.and.bubble.right.fill")
                    .font(.title3)
                    .foregroundStyle(RFColors.fallbackTextSecondary)
                    .frame(width: 36, height: 36)
                    .background(RFColors.fallbackSurface)
                    .clipShape(RoundedRectangle(cornerRadius: RFCornerRadius.medium))

                VStack(alignment: .leading, spacing: RFSpacing.xxs) {
                    primaryTitle
                    secondaryTitle
                }
                .frame(maxWidth: .infinity, alignment: .leading)

                Spacer(minLength: 0)
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel(accessibilityText)
    }

    // MARK: - Subviews

    @ViewBuilder
    private var primaryTitle: some View {
        let displayed = session.displayTitle
        let isAI = session.hasAITitle

        HStack(spacing: RFSpacing.xs) {
            RFText(displayed, style: .headline)
                .lineLimit(2)
                .id(displayed) // baslik degisince transition tetiklenir
                .transition(titleTransition)

            if isAI {
                aiBadge
                    .transition(badgeTransition)
            }
        }
    }

    @ViewBuilder
    private var secondaryTitle: some View {
        if session.hasAITitle {
            // AI baslik varken raw title secondary metin olarak gorunur.
            RFText(session.title, style: .caption, color: RFColors.fallbackTextTertiary)
                .lineLimit(1)
        } else if session.aiTitle == nil {
            // Henuz AI baslik uretilmedi — placeholder.
            RFText(
                String(localized: "home.session.aiTitle.placeholder"),
                style: .caption,
                color: RFColors.fallbackTextTertiary
            )
            .accessibilityHint(String(localized: "home.session.aiTitle.placeholder.a11y"))
        }
    }

    private var aiBadge: some View {
        RFText(
            String(localized: "home.session.aiTitle.badge"),
            style: .captionBold,
            color: .white
        )
        .padding(.horizontal, RFSpacing.xs)
        .padding(.vertical, 2)
        .background(RFColors.brandGradient)
        .clipShape(Capsule())
        .accessibilityLabel(String(localized: "home.session.aiTitle.badge.a11y"))
    }

    /// Reduce Motion aktifse sade opacity transition'a duser, aksi takdirde
    /// hafif scale ile birlestirilmis daha canli bir gecis kullanir.
    private var titleTransition: AnyTransition {
        reduceMotion
            ? .opacity
            : .opacity.combined(with: .scale(scale: 1.05))
    }

    private var badgeTransition: AnyTransition {
        reduceMotion
            ? .opacity
            : .opacity.combined(with: .scale(scale: 0.8))
    }

    private var accessibilityText: String {
        if session.hasAITitle {
            return String(
                format: String(localized: "home.session.row.a11yWithAI"),
                session.displayTitle,
                session.title
            )
        } else {
            return String(
                format: String(localized: "home.session.row.a11yFallback"),
                session.displayTitle
            )
        }
    }
}

#Preview("with AI title") {
    HomeSessionRow(
        session: HomeSession(
            id: "00000000-0000-0000-0000-000000000001",
            title: "ilk mesaj: backend testleri yesil mi?",
            aiTitle: "Backend test sonuclarinin incelenmesi",
            lastActivity: Date()
        )
    )
    .padding()
    .background(Color.black.opacity(0.2))
}

#Preview("fallback only") {
    HomeSessionRow(
        session: HomeSession(
            id: "00000000-0000-0000-0000-000000000002",
            title: "Yeni session",
            aiTitle: nil,
            lastActivity: Date()
        )
    )
    .padding()
    .background(Color.black.opacity(0.2))
}
