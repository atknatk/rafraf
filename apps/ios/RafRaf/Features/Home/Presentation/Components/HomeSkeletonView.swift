import SwiftUI

/// Home ekrani icin skeleton yukleme gorunumu.
/// Gercek icerik yapisini taklit eder — algisal olarak daha hizli yuklenme hissi.
struct HomeSkeletonView: View {
    var body: some View {
        VStack(spacing: RFSpacing.lg) {
            // Hero card skeleton
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: RFSpacing.xs) {
                    RoundedRectangle(cornerRadius: 4)
                        .fill(Color.white.opacity(0.2))
                        .frame(width: 160, height: 24)
                    RoundedRectangle(cornerRadius: 4)
                        .fill(Color.white.opacity(0.12))
                        .frame(width: 200, height: 14)
                }
                Spacer()
                Circle()
                    .fill(Color.white.opacity(0.12))
                    .frame(width: 64, height: 64)
            }
            .padding(RFSpacing.lg)
            .background {
                RoundedRectangle(cornerRadius: RFCornerRadius.extraLarge)
                    .fill(RFColors.fallbackTextTertiary.opacity(0.15))
            }
            .rfShimmer(isActive: true)

            // Quick actions skeleton
            HStack(spacing: RFSpacing.sm) {
                actionSkeleton
                actionSkeleton
            }
        }
        .padding(.horizontal, RFSpacing.md)
        .padding(.top, RFSpacing.xl)
    }

    private var actionSkeleton: some View {
        RFCard {
            HStack(spacing: RFSpacing.sm) {
                RoundedRectangle(cornerRadius: RFCornerRadius.medium)
                    .fill(RFColors.fallbackTextTertiary.opacity(0.2))
                    .frame(width: 40, height: 40)
                RoundedRectangle(cornerRadius: 4)
                    .fill(RFColors.fallbackTextTertiary.opacity(0.2))
                    .frame(width: 60, height: 14)
                Spacer()
            }
        }
        .rfShimmer(isActive: true)
    }
}

#Preview {
    ZStack {
        LinearGradient(
            colors: [RFColors.heroGradientStart, RFColors.heroGradientEnd],
            startPoint: .top,
            endPoint: .bottom
        )
        .ignoresSafeArea()

        HomeSkeletonView()
    }
}
