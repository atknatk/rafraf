import SwiftUI

/// Chat ekrani icin skeleton yukleme gorunumu.
/// Mesaj balonlari yapisini taklit eder.
struct ChatSkeletonView: View {
    var body: some View {
        VStack(spacing: RFSpacing.sm) {
            // AI message skeleton
            messageSkeleton(isUser: false, width: 220)
            // User message skeleton
            messageSkeleton(isUser: true, width: 180)
            // AI message skeleton (longer)
            messageSkeleton(isUser: false, width: 260)

            Spacer()
        }
        .padding(.horizontal, RFSpacing.md)
        .padding(.vertical, RFSpacing.sm)
        .rfShimmer(isActive: true)
    }

    private func messageSkeleton(isUser: Bool, width: CGFloat) -> some View {
        HStack {
            if isUser { Spacer() }

            VStack(alignment: isUser ? .trailing : .leading, spacing: RFSpacing.xxs) {
                RoundedRectangle(cornerRadius: RFCornerRadius.large)
                    .fill(
                        isUser
                            ? RFColors.userBubble.opacity(0.5)
                            : RFColors.aiBubble.opacity(0.5)
                    )
                    .frame(width: width, height: 44)

                RoundedRectangle(cornerRadius: 4)
                    .fill(RFColors.fallbackTextTertiary.opacity(0.15))
                    .frame(width: 50, height: 10)
            }

            if !isUser { Spacer() }
        }
    }
}

#Preview {
    ChatSkeletonView()
        .background(RFColors.fallbackBackground)
}
