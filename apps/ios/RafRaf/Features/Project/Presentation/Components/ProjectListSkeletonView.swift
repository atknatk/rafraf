import SwiftUI

/// Proje listesi icin skeleton yukleme gorunumu.
/// Kart yapisini taklit eder.
struct ProjectListSkeletonView: View {
    var body: some View {
        ScrollView {
            VStack(spacing: RFSpacing.sm) {
                ForEach(0..<4, id: \.self) { _ in
                    projectCardSkeleton
                }
            }
            .padding(.horizontal, RFSpacing.md)
            .padding(.vertical, RFSpacing.sm)
        }
    }

    private var projectCardSkeleton: some View {
        RFCard {
            VStack(alignment: .leading, spacing: RFSpacing.sm) {
                HStack {
                    RoundedRectangle(cornerRadius: 4)
                        .fill(RFColors.fallbackTextTertiary.opacity(0.3))
                        .frame(width: 140, height: 18)
                    Spacer()
                    RoundedRectangle(cornerRadius: RFCornerRadius.pill)
                        .fill(RFColors.fallbackTextTertiary.opacity(0.2))
                        .frame(width: 70, height: 22)
                }

                RoundedRectangle(cornerRadius: 4)
                    .fill(RFColors.fallbackTextTertiary.opacity(0.2))
                    .frame(height: 14)

                HStack(spacing: RFSpacing.xxs) {
                    ForEach(0..<3, id: \.self) { _ in
                        RoundedRectangle(cornerRadius: RFCornerRadius.pill)
                            .fill(RFColors.fallbackTextTertiary.opacity(0.15))
                            .frame(width: CGFloat.random(in: 50...80), height: 20)
                    }
                }
            }
        }
        .rfShimmer(isActive: true)
    }
}

#Preview {
    ProjectListSkeletonView()
}
