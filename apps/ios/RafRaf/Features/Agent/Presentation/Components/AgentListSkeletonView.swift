import SwiftUI

/// Agent listesi icin skeleton yukleme gorunumu.
struct AgentListSkeletonView: View {
    var body: some View {
        ScrollView {
            VStack(spacing: RFSpacing.sm) {
                ForEach(0..<3, id: \.self) { _ in
                    agentCardSkeleton
                }
            }
            .padding(.horizontal, RFSpacing.md)
            .padding(.vertical, RFSpacing.sm)
        }
    }

    private var agentCardSkeleton: some View {
        RFCard {
            VStack(alignment: .leading, spacing: RFSpacing.sm) {
                HStack {
                    VStack(alignment: .leading, spacing: RFSpacing.xxs) {
                        RoundedRectangle(cornerRadius: 4)
                            .fill(RFColors.fallbackTextTertiary.opacity(0.3))
                            .frame(width: 120, height: 18)
                        RoundedRectangle(cornerRadius: 4)
                            .fill(RFColors.fallbackTextTertiary.opacity(0.2))
                            .frame(width: 90, height: 14)
                    }
                    Spacer()
                    RoundedRectangle(cornerRadius: RFCornerRadius.pill)
                        .fill(RFColors.fallbackTextTertiary.opacity(0.2))
                        .frame(width: 70, height: 22)
                }

                HStack(spacing: RFSpacing.xxs) {
                    ForEach(0..<4, id: \.self) { _ in
                        RoundedRectangle(cornerRadius: RFCornerRadius.pill)
                            .fill(RFColors.fallbackTextTertiary.opacity(0.15))
                            .frame(width: CGFloat.random(in: 50...70), height: 20)
                    }
                }

                VStack(spacing: RFSpacing.xs) {
                    ForEach(0..<3, id: \.self) { _ in
                        RoundedRectangle(cornerRadius: RFCornerRadius.small)
                            .fill(RFColors.fallbackTextTertiary.opacity(0.15))
                            .frame(height: 6)
                    }
                }
            }
        }
        .rfShimmer(isActive: true)
    }
}

#Preview {
    AgentListSkeletonView()
}
